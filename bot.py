from config import *
import texts
import json
import logging
import telegram
from collections import OrderedDict  # , namedtuple
from telegram.ext import Updater, CommandHandler, ConversationHandler, MessageHandler, RegexHandler, Filters


class Entity:
    def __init__(self, entity_dict=None):
        if entity_dict is None:
            self._dict = OrderedDict()
        else:
            self._dict = entity_dict
            for key, value in entity_dict.items():
                setattr(self, key, value)

    # def __getattr__(self, key):
    #     return self._dict[key]
    #
    # def __setattr__(self, key, value):
    #     self._dict[key] = value

    def __bool__(self):
        return bool(self._dict)
        # return True if self._dict else False

    def __hash__(self):
        return hash(repr(self))

    def __eq__(self, other):
        return self._dict == other._dict

    def __str__(self):
        return texts.entity % (self.description, self.stock, self.price)

    def __repr__(self):
        return "Entity(" + (", ".join("%s=%s" % (k, v) for k, v in self._dict.items())) + ")"


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

    # def __iter__(self):
    #     return self

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
        return repr(self._catalog)
        # return str(self)


class Cart:
    def __init__(self, items=None):
        self.items = OrderedDict()
        self.sum = 0
        if items:
            for p, q in items.items():
                self.items[p] = q
                self.sum += p.price * q

    def add(self, product=None, quantity=0):
        # TODO: check if there is enough goods in stock
        if product:
            if quantity == 0:
                quantity = 1
            if product in self.items:
                self.items[product] += quantity
            else:
                self.items[product] = quantity
            self.sum += product.price * quantity

    def delete(self, product=None, quantity=0):
        if product:
            if quantity == 0:
                quantity = 1
            if product in self.items:
                if self.items[product] > quantity:
                    self.items[product] -= quantity
                    self.sum -= product.price * quantity
                else:
                    self.sum -= product.price * self.items[product]
                    del self.items[product]

    def __getitem__(self, item):
        return self.items[item] if item in self.items else 0

    def __bool__(self):
        return bool(self.items)

    def __add__(self, other):
        return Cart(self.items).add(other)

    def __sub__(self, other):
        return Cart(self.items).delete(other)

    def __iadd__(self, other):
        self.add(other)

    def __isub__(self, other):
        self.delete(other)

    def __str__(self):
        return "\n\n".join(str(i+1)+". "+(texts.cart_items % (p.description, q, p.price, p.price*q)) for i, (p, q) in enumerate(self.items.items())) if self else texts.empty_cart


# constant for sending 'typing...'
typing = telegram.ChatAction.TYPING

########################################################################################################################
# тестовый каталог
# paper_a1 = Entity("лист формата А1", "123123", 14, 40)
# paper_a2 = Entity("лист формата А2", "12ыв3", 8, 61)
# paper_a3 = Entity("лист формата А3", "12sdыв3", 4, 84)
# paper_a4 = Entity("лист формата А4", "12sddasыв3", 2, 1254)
#
# pen_1 = Entity("ручка обычная", "18asыв3", 2, 45)
# pen_2 = Entity("ручка Илитная", "18asй3", 222, 6)
#
# notebook_hp = Entity("ноутбук HP", "zx18c3", 68000, 14)
# notebook_apple = Entity("ноутбук Apple", "zx2134", 98000, 4)
# smartphone = Entity("Asus Zenfone 2 Lazer", "z2x12c12", 10400, 2)

# paper_a1 = {"description": "лист формата А1", "img": "123123", "price": 14, "stock": 40}
# paper_a2 = {"description": "лист формата А2", "img": "12ыв3", "price": 8, "stock": 61}
# paper_a3 = {"description": "лист формата А3", "img": "12sdыв3", "price": 4, "stock": 84}
# paper_a4 = {"description": "лист формата А4", "img": "12sddasыв3", "price": 2, "stock": 1254}
#
# pen_1 = {"description": "ручка обычная", "img": "18asыв3", "price": 2, "stock": 45}
# pen_2 = {"description": "ручка Илитная", "img": "18asй3", "price": 222, "stock": 6}
#
# notebook_hp = {"description": "ноутбук HP", "img": "zx18c3", "price": 68000, "stock": 14}
# notebook_apple = {"description": "ноутбук Apple", "img": "zx2134", "price": 98000, "stock": 4}
# smartphone = {"description": "Asus Zenfone 2 Lazer", "img": "z2x12c12", "price": 10400, "stock": 2}
#
# strange_stuff = {"description": "непонятное барахло", "img": "", "price": 12, "stock": 12}
#
# fake_catalog = {"канцтовары": {"бумага": [paper_a1, paper_a2, paper_a3, paper_a4], "другое": [pen_1, pen_2]},
#                 "техника": {"электроника": [notebook_apple, notebook_hp, smartphone], "другое": [strange_stuff]}}

# save fake catalog as json
# with open('data.json', 'w', encoding='utf8') as fp:
#     json.dump(catalog, fp, ensure_ascii=False, indent=4)
# exit()

########################################################################################################################

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
from telegram import InlineKeyboardButton as ikb

ik = [[ikb(texts.prev_btn, callback_data="<"), ikb(texts.next_btn, callback_data=">")],
      [ikb(texts.show_img_btn, callback_data="img")], [ikb(texts.to_cart_btn, callback_data="to_cart")]]


def simple_answer(text, keyboard=None, inlinekeyboard=None, next_state=None):
    if keyboard:
        def answer_function(bot, update):
            uid = update.message.from_user.id
            bot.sendChatAction(uid, action=typing)
            bot.sendMessage(uid, text=text, parse_mode="HTML", reply_markup=kbd(keyboard))
            print("going to next_state = " + str(next_state))
            return next_state
    elif inlinekeyboard:
        def answer_function(bot, update):
            uid = update.message.from_user.id
            bot.sendChatAction(uid, action=typing)
            bot.sendMessage(uid, text=text, parse_mode="HTML",
                            reply_markup=telegram.InlineKeyboardMarkup(inlinekeyboard))
            print("going to next_state = " + str(next_state))
            return next_state
    else:
        def answer_function(bot, update):
            uid = update.message.from_user.id
            bot.sendChatAction(uid, action=typing)
            bot.sendMessage(uid, text=text, parse_mode="HTML")
            print("going to next_state = " + str(next_state))
            return next_state
    return answer_function


def start(bot, update, user_data):
    uid = update.message.from_user.id
    bot.sendChatAction(uid, action=typing)
    if 'first_name' not in user_data:
        if uid == owner_id:
            text = texts.welcome_admin
            keyboard = main_kbd_admin
        else:
            text = texts.welcome_user
            keyboard = send_contact_kbd
            user_data['first_name'] = update.message.from_user.first_name
            user_data['last_name'] = update.message.from_user.last_name
            user_data["cart"] = Cart()
        bot.sendMessage(update.message.chat_id, text=text, parse_mode="HTML", reply_markup=kbd(keyboard))
        return "MAIN_MENU_A" if uid == owner_id else "CHECK"
    else:
        bot.sendMessage(uid, text=texts.welcome_again_user, parse_mode="HTML", reply_markup=kbd(main_kbd_user))


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
    simple_answer(text=texts.cart_welcome)(bot, update)
    simple_answer(text=str(user_data["cart"]), keyboard=main_kbd_user)(bot, update)
    return "MAIN_MENU_U"
    # bot.sendMessage(update.message.chat_id, text=str(cart), parse_mode="HTML", reply_markup=kbd(main_kbd_user))


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
    act = update.callback_query.data
    scroll = user_data["scroll"]
    cart = user_data["cart"]

    if act == '>':
        next_e = scroll.get_next()
        if next_e:
            bot.answerCallbackQuery(callback_query_id=cqid)
            bot.editMessageText(text=str(next_e), chat_id=update.callback_query.message.chat.id,
                                message_id=update.callback_query.message.message_id,
                                reply_markup=telegram.InlineKeyboardMarkup(ik), parse_mode="HTML")
        else:
            bot.answerCallbackQuery(text=texts.last_item, callback_query_id=cqid)

    elif act == '<':
        prev_e = scroll.get_prev()
        if prev_e:
            bot.answerCallbackQuery(callback_query_id=cqid)
            bot.editMessageText(text=str(prev_e), chat_id=update.callback_query.message.chat.id,
                                message_id=update.callback_query.message.message_id,
                                reply_markup=telegram.InlineKeyboardMarkup(ik), parse_mode="HTML")
        else:
            bot.answerCallbackQuery(text=texts.first_item, callback_query_id=cqid)

    elif act == 'img':
        bot.answerCallbackQuery(callback_query_id=cqid)
        bot.sendPhoto(chat_id=update.callback_query.message.chat.id, photo=scroll.get_current().img,
                      caption=scroll.get_current().description)
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
                         RegexHandler(texts.main_menu_btn, lambda b, u: simple_answer(text=texts.in_main_menu, keyboard=main_kbd_user, next_state="MAIN_MENU_U")(b, u))],

    }

    # (bot, update, user_data=None, text=None, inlinekeyboard=None, next_state=None, subcat=None)

    # for cat in flatten(catalog.categories_kbd):
    #     states["CATALOG_"+cat] = [RegexHandler(btn,
    #         lambda bot, update, user_data:
    #             catalog_item(bot, update, user_data=user_data, text=str(catalog[cat][btn][0]), inlinekeyboard=ik, subcat=catalog[cat][btn]),
    #                                            pass_user_data=True) for btn in flatten(catalog.subcat_kbd[cat])]

    for cat in flatten(catalog.categories_kbd):
        states["CATALOG_" + cat] = [cqh]
        for btn in flatten(catalog.subcat_kbd[cat]):
            print(cat, btn)
            fff = lambda bot, update, user_data: catalog_item(bot, update, user_data=user_data,
                                                              text=str(catalog[str(cat)][str(btn)][0]),
                                                              inlinekeyboard=ik, subcat=catalog[cat][btn])
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

    # inline keyboard handler
    # cqh = telegram.ext.CallbackQueryHandler(inline, pass_user_data=True)
    # dp.add_handler(cqh)

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
