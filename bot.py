from config import *
import texts
import json
import logging
import telegram
from collections import OrderedDict  # , namedtuple
from telegram.ext import Updater, CommandHandler, ConversationHandler, MessageHandler, RegexHandler, Filters
from telegram import InlineKeyboardButton as ikb
from telegram import InlineKeyboardMarkup as ik


class Entity:
    def __init__(self, entity_dict=None):
        if entity_dict is None:
            self._dict = OrderedDict()
        else:
            self._dict = entity_dict
            for key, value in entity_dict.items():
                setattr(self, key, value)

    def __bool__(self):
        return bool(self._dict)

    def __hash__(self):
        return hash(repr(self))

    def __eq__(self, other):
        return self._dict == other._dict

    def __str__(self):
        return texts.entity % (self.description, self.stock, self.price)

    def __repr__(self):
        return "Entity(" + (", ".join("%s='%s'" % (k, v) for k, v in self._dict.items())) + ")"


class SubCat:
    def __init__(self, collection):
        self.item = tuple(collection)
        self.index = 0

    def get_current(self):
        return self.item[self.index]

    def get_next(self):
        if self.index < len(self.item) - 1:
            self.index += 1
            return self.item[self.index]
        else:
            return Entity()

    def get_prev(self):
        if self.index > 0:
            self.index -= 1
            return self.item[self.index]
        else:
            return Entity()

    def copy(self):
        return SubCat(self.item)

    def __getitem__(self, key):
        return self.item[key]

    def __str__(self):
        return str(self.item)

    def __repr__(self):
        return str(self)


class Catalog:
    def __init__(self, catalog_dict):
        self._catalog = OrderedDict()
        self.categories_kbd = list([k] for k in catalog_dict.keys())
        self.subcat_kbd = OrderedDict()

        for category_name, category_dict in catalog_dict.items():
            self._catalog[category_name] = OrderedDict()
            self.subcat_kbd[category_name] = [[scn] for scn in category_dict.keys()]
            for subcat_name, subcat_dict in category_dict.items():
                self._catalog[category_name][subcat_name] = SubCat(Entity(item) for item in subcat_dict)

    def __getitem__(self, key):
        return self._catalog[key]

    def __str__(self):
        return str(self._catalog)

    def __repr__(self):
        return "Catalog(" + repr(self._catalog) + ")"


class Cart:
    def __init__(self, items=None):
        self.items = OrderedDict()
        if items:
            for p, q in items.items():
                self.items[p] = q

    @property
    def total(self):
        return sum(p.price*q for p, q in self.items.items())

    def add(self, product=None, quantity=0):
        # TODO: check if there is enough goods in stock
        if product:
            if quantity == 0:
                quantity = 1
            if product in self.items:
                self.items[product] += quantity
            else:
                self.items[product] = quantity

    def delete(self, product=None, quantity=0):
        if product:
            if quantity == 0:
                quantity = 1
            if product in self.items:
                if self.items[product] > quantity:
                    self.items[product] -= quantity
                else:
                    del self.items[product]

    def str_repr(self):
        return [str(i+1)+". "+(texts.cart_items % (p.description, q, p.price, p.price*q))
                for i, (p, q) in enumerate(self.items.items())]

    def __getitem__(self, item):
        try:
            it = iter(self.items.keys())
            for i in range(item+1):
                e = next(it)
            return e
        except TypeError:
            return self.items[item] if item in self.items else 0

    def __delitem__(self, key):
        try:
            it = iter(self.items.keys())
            for i in range(key+1):
                e = next(it)
            del self.items[e]
        except TypeError:
            del self.items[key]

    def __contains__(self, item):
        try:
            return 0 <= item < len(self.items)
        except TypeError:
            return item in self.items

    def __bool__(self):
        return bool(self.items)

    def __add__(self, other):
        return Cart(self.items).add(other)

    def __sub__(self, other):
        return Cart(self.items).delete(other)

    def __iadd__(self, other):
        self.add(other)
        return self

    def __isub__(self, other):
        self.delete(other)
        return self

    def __str__(self):
        return "\n\n".join(self.str_repr())

    def __len__(self):
        return sum(q for q in self.items.values())


# constant for sending 'typing...'
typing = telegram.ChatAction.TYPING

with open('data.json', 'r', encoding='utf8') as fp:
    catalog = Catalog(json.load(fp, object_pairs_hook=OrderedDict))

# Enable logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger('TrainRunnerBot.' + __name__)


def kbd(k):
    return telegram.ReplyKeyboardMarkup(k, one_time_keyboard=True, resize_keyboard=True)


def flatten(nl):
    return [item for sublist in nl for item in sublist]

# keyboards
send_contact_kbd = [[telegram.KeyboardButton(texts.send_contact, request_contact=True)]]
main_kbd_user = [[texts.catalog_btn_user, texts.cart_btn_user],
                 [texts.orders_btn_user, texts.info_btn_user]]
main_kbd_admin = [[texts.orders_btn_admin, texts.edit_btn_admin],
                  [texts.stat_btn_admin, texts.info_btn_admin]]
to_cart_kbd = [[texts.confirm_order_btn], [texts.to_cat_btn], [texts.main_menu_btn]]

# inline keyboard for catalog
catalog_ikbd = [[ikb(texts.prev_btn, callback_data="<"), ikb(texts.next_btn, callback_data=">")],
                [ikb(texts.show_img_btn, callback_data="img")], [ikb(texts.to_cart_btn, callback_data="to_cart")]]
# inline keyboard for cart
cart_item_ikbd = [[ikb(texts.cart_item_dec1_btn, callback_data="cart-1"),
                   ikb(texts.cart_item_del_btn, callback_data="cart_del"),
                   ikb(texts.cart_item_inc1_btn, callback_data="cart+1")]]
# inline keyboard for cart summary
cart_sum_ikbd = [[ikb(texts.cart_decline_btn, callback_data="del_all"),
                  ikb(texts.cart_confirm_btn, callback_data="confirm_all")]]


def simple_answer(text, keyboard=None, inlinekeyboard=None, next_state=None):
    if keyboard:
        def answer_function(bot, update):
            uid = update.message.from_user.id
            bot.sendChatAction(uid, action=typing)
            bot.sendMessage(uid, text=text, parse_mode="HTML", reply_markup=kbd(keyboard))
            # print("going to next_state = " + str(next_state))
            return next_state
    elif inlinekeyboard:
        def answer_function(bot, update):
            uid = update.message.from_user.id
            bot.sendChatAction(uid, action=typing)
            bot.sendMessage(uid, text=text, parse_mode="HTML",
                            reply_markup=ik(inlinekeyboard))
            # print("going to next_state = " + str(next_state))
            return next_state
    else:
        def answer_function(bot, update):
            uid = update.message.from_user.id
            bot.sendChatAction(uid, action=typing)
            bot.sendMessage(uid, text=text, parse_mode="HTML")
            # print("going to next_state = " + str(next_state))
            return next_state
    return answer_function


def start(bot, update, user_data):
    uid = update.message.from_user.id
    bot.sendChatAction(uid, action=typing)
    if uid == owner_id:
        text = texts.welcome_admin
        keyboard = main_kbd_admin
        next_state = "MAIN_MENU_A"
    else:
        if 'first_name' not in user_data:
            user_data['first_name'] = update.message.from_user.first_name
            user_data['last_name'] = update.message.from_user.last_name
            user_data["cart"] = Cart()
            text = texts.welcome_user
        else:
            text = texts.welcome_again_user
        keyboard = main_kbd_user
        next_state = "MAIN_MENU_U"
    return simple_answer(text=text, keyboard=keyboard, next_state=next_state)(bot, update)


def main_menu_user(bot, update, user_data):
    uid = update.message.from_user.id
    bot.sendChatAction(uid, action=typing)
    user_data['phone'] = update.message.contact.phone_number
    bot.sendMessage(update.message.chat_id, text=texts.contact_ok, parse_mode="HTML", reply_markup=kbd(main_kbd_user))
    return "MAIN_MENU_U"


def no_contact(bot, update):
    uid = update.message.from_user.id
    bot.sendChatAction(uid, action=typing)
    bot.sendSticker(uid, sticker=texts.sticker)
    bot.sendMessage(uid, text=texts.contact_err, parse_mode="HTML", reply_markup=kbd(send_contact_kbd))


def orders_admin(bot, update):
    uid = update.message.from_user.id
    bot.sendChatAction(uid, action=typing)
    bot.sendMessage(update.message.chat_id, text='orders', parse_mode="HTML", reply_markup=kbd(main_kbd_user))


def edit_admin(bot, update):
    uid = update.message.from_user.id
    bot.sendChatAction(uid, action=typing)
    bot.sendMessage(update.message.chat_id, text='edit', parse_mode="HTML", reply_markup=kbd(main_kbd_user))


def stat_admin(bot, update):
    uid = update.message.from_user.id
    bot.sendChatAction(uid, action=typing)
    bot.sendMessage(update.message.chat_id, text='stat', parse_mode="HTML", reply_markup=kbd(main_kbd_user))


def info_admin(bot, update):
    uid = update.message.from_user.id
    bot.sendChatAction(uid, action=typing)
    bot.sendMessage(update.message.chat_id, text=texts.info_admin, parse_mode="HTML", reply_markup=kbd(main_kbd_user))


def catalog_user(bot, update):
    return simple_answer(text=texts.select_category, keyboard=catalog.categories_kbd, next_state="CATALOG")(bot, update)


def catalog_item(bot, update, user_data=None, text=None, inlinekeyboard=None, next_state=None, subcat=None):
    # TODO: Hide prev inline kbd
    user_data["scroll"] = subcat.copy()
    return simple_answer(text=text, inlinekeyboard=inlinekeyboard, next_state=next_state)(bot, update)


def cart_user(bot, update, user_data):
    uid = update.message.from_user.id
    cart = user_data["cart"]

    if cart:
        simple_answer(text=texts.cart_welcome)(bot, update)
        msgs = []
        for item in user_data["cart"].str_repr():
            bot.sendChatAction(uid, action=typing)
            msgs.append(bot.sendMessage(uid, text=item, parse_mode="HTML", reply_markup=ik(cart_item_ikbd)))
        user_data["cart_map"] = [msg.message_id for msg in msgs]
        user_data["cart_sum"] = bot.sendMessage(uid, text=texts.cart_sum % (len(cart), cart.total),
                                                reply_markup=ik(cart_sum_ikbd), parse_mode="HTML").message_id
    else:
        simple_answer(text=texts.empty_cart, keyboard=main_kbd_user)(bot, update)
    return "MAIN_MENU_U"


def orders_user(bot, update):
    uid = update.message.from_user.id
    bot.sendChatAction(uid, action=typing)
    bot.sendMessage(update.message.chat_id, text='orders', parse_mode="HTML", reply_markup=kbd(main_kbd_user))


def info_user(bot, update):
    uid = update.message.from_user.id
    bot.sendChatAction(uid, action=typing)
    bot.sendMessage(update.message.chat_id, text=texts.info_user, parse_mode="HTML", reply_markup=kbd(main_kbd_user))


def inline(bot, update, user_data):
    uid = update.callback_query.from_user.id
    cqid = update.callback_query.id
    chat_id = update.callback_query.message.chat.id
    message_id = update.callback_query.message.message_id
    act = update.callback_query.data
    scroll = user_data["scroll"]
    cart = user_data["cart"]

    if act == '>':
        next_e = scroll.get_next()
        if next_e:
            bot.answerCallbackQuery(callback_query_id=cqid)
            bot.editMessageText(text=str(next_e), chat_id=chat_id, message_id=message_id,
                                reply_markup=ik(catalog_ikbd), parse_mode="HTML")
        else:
            bot.answerCallbackQuery(text=texts.last_item, callback_query_id=cqid)

    elif act == '<':
        prev_e = scroll.get_prev()
        if prev_e:
            bot.answerCallbackQuery(callback_query_id=cqid)
            bot.editMessageText(text=str(prev_e), chat_id=chat_id, message_id=message_id,
                                reply_markup=ik(catalog_ikbd), parse_mode="HTML")
        else:
            bot.answerCallbackQuery(text=texts.first_item, callback_query_id=cqid)

    elif act == 'img':
        bot.answerCallbackQuery(callback_query_id=cqid)
        bot.sendPhoto(chat_id=chat_id, photo=scroll.get_current().img, caption=scroll.get_current().description)
        # TODO: send the message with scrollable list again
        # TODO: decrease "stock" value

    elif act == "to_cart":
        current = scroll.get_current()
        if cart[current] < current.stock:
            bot.answerCallbackQuery(callback_query_id=cqid)
            cart += current
            bot.sendMessage(uid, text=texts.to_cart_done, parse_mode="HTML", reply_markup=kbd(to_cart_kbd))
            return "TO_CART_DONE"
        else:
            bot.answerCallbackQuery(text=texts.not_enough_in_stock, callback_query_id=cqid)

    elif act == "cart_del":
        bot.answerCallbackQuery(callback_query_id=cqid)
        dn = user_data["cart_map"].index(message_id)
        del user_data["cart_map"][dn]
        del cart[dn]
        user_data["cart"] = cart
        bot.editMessageText(text=texts.cart_item_deleted, chat_id=chat_id, message_id=message_id,
                            reply_markup=ik([]), parse_mode="HTML")

    elif act == "cart-1":
        pass

    elif act == "cart+1":
        index = user_data["cart_map"].index(message_id)
        add_item = cart[index]
        if cart[add_item] + 1 <= add_item.stock:
            cart += add_item
            bot.editMessageText(text=cart.str_repr()[index], chat_id=chat_id, message_id=message_id,
                                reply_markup=ik(cart_item_ikbd), parse_mode="HTML")
            bot.editMessageText(text=texts.cart_sum % (len(cart), cart.total), chat_id=chat_id, message_id=user_data["cart_sum"],
                                reply_markup=ik(cart_sum_ikbd), parse_mode="HTML")
            bot.answerCallbackQuery(callback_query_id=cqid)
        else:
            bot.answerCallbackQuery(text=texts.not_enough_in_stock, callback_query_id=cqid)

    elif act == "del_all":
        for mid in user_data["cart_map"]+[user_data["cart_sum"]]:
            bot.editMessageText(text=texts.cart_item_deleted, chat_id=chat_id, message_id=mid, parse_mode="HTML")
        bot.answerCallbackQuery(callback_query_id=cqid)
        user_data["cart"] = Cart()
        del user_data["cart_map"]
        del user_data["cart_sum"]

    elif act == "confirm_all":
        pass


def error(bot, update, err):
    logger.warn('Update "%s" caused error "%s"' % (update, err))


def load_data():
    pass
    # load catalog from JSON
    # with open('data.json', 'r', encoding='utf8') as fp:
    #     catalog = Catalog(json.load(fp, object_pairs_hook=OrderedDict))
    # return catalog


def save_data():
    pass


def main():
    # Create the EventHandler and pass it your bot's token.
    updater = Updater(telegram_token)
    # Get the dispatcher to register handlers
    dp = updater.dispatcher

    # catalog = load_data()

    cqh = telegram.ext.CallbackQueryHandler(inline, pass_user_data=True)

    states = {
        "CHECK": [MessageHandler(Filters.contact, main_menu_user, pass_user_data=True),
                  MessageHandler(Filters.text, no_contact)],

        "MAIN_MENU_A": [RegexHandler(texts.orders_btn_admin, orders_admin),
                        RegexHandler(texts.edit_btn_admin, edit_admin),
                        RegexHandler(texts.stat_btn_admin, stat_admin),
                        RegexHandler(texts.info_btn_admin, info_admin)],

        "MAIN_MENU_U": [RegexHandler(texts.catalog_btn_user, catalog_user),
                        RegexHandler(texts.cart_btn_user, cart_user, pass_user_data=True),
                        RegexHandler(texts.orders_btn_user, orders_user),
                        RegexHandler(texts.info_btn_user, info_user)],

        "CATALOG": [
            RegexHandler(btn, simple_answer(text=texts.select_subcategory % btn, keyboard=catalog.subcat_kbd[btn],
                                            next_state="CATALOG_" + btn))
            for btn in flatten(catalog.categories_kbd)],
        "TO_CART_DONE": [RegexHandler(texts.confirm_order_btn, cart_user, pass_user_data=True),
                         RegexHandler(texts.to_cat_btn, catalog_user),
                         RegexHandler(texts.main_menu_btn, lambda b, u: simple_answer(
                             text=texts.in_main_menu, keyboard=main_kbd_user, next_state="MAIN_MENU_U")(b, u))],

    }

    # (bot, update, user_data=None, text=None, inlinekeyboard=None, next_state=None, subcat=None)

    # for cat in flatten(catalog.categories_kbd):
    #     states["CATALOG_"+cat] = [RegexHandler(btn,
    #         lambda bot, update, user_data:
    #             catalog_item(bot, update, user_data=user_data, text=str(catalog[cat][btn][0]), inlinekeyboard=catalog_ikbd, subcat=catalog[cat][btn]),
    #                                            pass_user_data=True) for btn in flatten(catalog.subcat_kbd[cat])]

    for cat in flatten(catalog.categories_kbd):
        states["CATALOG_" + cat] = [cqh]
        for btn in flatten(catalog.subcat_kbd[cat]):
            # print(cat, btn)
            fff = lambda bot, update, user_data: catalog_item(bot, update, user_data=user_data,
                                                              text=str(catalog[str(cat)][str(btn)][0]),
                                                              inlinekeyboard=catalog_ikbd, subcat=catalog[cat][btn])
            states["CATALOG_" + cat].append(RegexHandler(btn, fff, pass_user_data=True))

    # for cc in flatten(catalog.categories_kbd):
    #     states["CATALOG_"+cc] = [RegexHandler(btn, lambda bot, update, user_data: print("cat = ", cc, ";\t btn = ", btn), pass_user_data=True) for btn in flatten(catalog.subcat_kbd[cc])]

    command_handlers = [CommandHandler('start', start, pass_user_data=True), ]

    # inline buttons and slash-commands must be handled from any chat state
    states = {k: v+command_handlers+[cqh] for k, v in states.items()}

    # Add conversation handler with the states
    conversation_handler = ConversationHandler(
        entry_points=command_handlers,
        states=states,
        fallbacks=[])

    # загрузка данных
    # load_data()
    dp.add_handler(conversation_handler)

    # log all errors
    dp.add_error_handler(error)

    # Start the Bot
    updater.start_polling()

    # Run the bot until the you presses Ctrl-C or the process receives SIGINT,
    # SIGTERM or SIGABRT. This should be used most of the time, since
    # start_polling() is non-blocking and will stop the bot gracefully.
    updater.idle()

    # сохранение данных
    save_data()
    # pickle.dump((chat, conversation_handler.conversations), open(conversations_file, mode='wb'))


if __name__ == '__main__':
    main()
