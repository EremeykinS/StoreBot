import io
import json
import pickle
import logging
import datetime
from collections import OrderedDict

import telegram
from telegram.ext import Updater, CommandHandler, ConversationHandler, MessageHandler, RegexHandler, Filters
# from telegram.contrib.botan import Botan
from telegram import InlineKeyboardButton as ikb
from telegram import InlineKeyboardMarkup as ik
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import matplotlib.pyplot as plt
from matplotlib import rc

import texts
from config import *
from models import Base, User, Order, Catalog, Cart

now = datetime.datetime.now
# constant for sending 'typing...'
typing = telegram.ChatAction.TYPING

# Enable logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger('StoreBot.' + __name__)

# botan
# btrack = Botan(botan_token).track

# keyboards
send_contact_kbd = [[telegram.KeyboardButton(texts.send_contact, request_contact=True)]]
main_kbd_user = [[texts.catalog_btn_user, texts.cart_btn_user],
                 [texts.orders_btn_user, texts.info_btn_user]]
main_kbd_admin = [[texts.orders_btn_admin, texts.edit_btn_admin],
                  [texts.stat_btn_admin, texts.info_btn_admin]]
to_cart_kbd = [[texts.confirm_order_btn], [texts.to_cat_btn], [texts.main_menu_btn]]
delivery_methods_kbd = [[texts.delivery_carrier_btn], [texts.delivery_pickup_btn]]
pickup_points = [[point] for point in texts.pickup_point]
orders_sort_kbd = [[texts.active_orders_btn], [texts.date_orders_btn], [texts.archive_orders_btn]]
order_status_kbd = [[texts.default_order_status], [texts.order_status_delivery], [texts.order_status_pickup],
                    [texts.order_status_completed], [texts.cancel_status_input_btn]]
stat_type_kbd = [[texts.static_stat_btn, texts.dynamic_stat_btn]]
to_item_list_kbd = [[texts.to_item_list_btn]]

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
# inline keyboard for admin to edit order status
edit_order_ikbd = [[ikb(texts.edit_order_status_btn, callback_data="edit_order_status")]]

with open('data.json', 'r', encoding='utf8') as fp:
    catalog = Catalog(json.load(fp, object_pairs_hook=OrderedDict))

engine = create_engine('postgresql://%s:%s@%s:%s/%s' % (db_username, db_password, db_host, db_port, db_name))
Session = sessionmaker(bind=engine)
session = Session()
Base.metadata.create_all(engine)

# matplotlib font settings
font = {'family': 'DejaVu Serif', 'weight': 'normal', 'size': 24} # avail_font_names = [f.name for f in matplotlib.font_manager.fontManager.ttflist]
rc('font', **font)


def kbd(k):
    return telegram.ReplyKeyboardMarkup(k, one_time_keyboard=True, resize_keyboard=True)


def flatten(nl):
    return [item for sublist in nl for item in sublist]


def correct_time(value):
    try:
        h, m = value.split(":")
        result = datetime.time(int(h), int(m))
    except ValueError:
        result = False
    finally:
        return result


def correct_date(value):
    try:
        d, m, y = value.split(".")
        result = datetime.date(year=int(y), month=int(m), day=int(d))
    except ValueError:
        result = False
    finally:
        return result


def ans(text, keyboard=None, inlinekeyboard=None, next_state=None):
    if keyboard:
        def answer_function(bot, update):
            try:
                uid = update.message.from_user.id
            except AttributeError:
                uid = update.callback_query.from_user.id
            bot.sendChatAction(uid, action=typing)
            bot.sendMessage(uid, text=text, parse_mode="HTML", reply_markup=kbd(keyboard))
            return next_state
    elif inlinekeyboard:
        def answer_function(bot, update):
            try:
                uid = update.message.from_user.id
            except AttributeError:
                uid = update.callback_query.from_user.id
            bot.sendChatAction(uid, action=typing)
            bot.sendMessage(uid, text=text, parse_mode="HTML",
                            reply_markup=ik(inlinekeyboard))
            return next_state
    else:
        def answer_function(bot, update):
            try:
                uid = update.message.from_user.id
            except AttributeError:
                uid = update.callback_query.from_user.id
            bot.sendChatAction(uid, action=typing)
            bot.sendMessage(uid, text=text, parse_mode="HTML")
            return next_state
    return answer_function


def saving_ans(text: str, name: str, keyboard=None, inlinekeyboard=None, next_state=None,
               checker=lambda x: True, error_text=None):
    def answer_function(bot, update, user_data):
        answer = update.message.text
        if checker(answer):
            user_data[name] = answer
            txt = text
            k = keyboard
            ik = inlinekeyboard
            n_s = next_state
        else:
            txt = error_text
            k = None
            ik = None
            n_s = None
        return ans(text=txt, keyboard=k, inlinekeyboard=ik, next_state=n_s)(bot, update)

    return answer_function


def start(bot, update, user_data):
    uid = update.message.from_user.id
    bot.sendChatAction(uid, action=typing)
    # btrack(update.message, event_name="start-test-inline")
    # if the user is admin
    if uid == owner_id:
        text = texts.welcome_admin
        keyboard = main_kbd_admin
        next_state = "MAIN_MENU_A"
    # if the user is an ordinary user (is not admin)
    else:
        # if user is not saved in user_data dict
        if 'user' not in user_data:
            # and the user is not saved in DB
            if session.query(User.tuid).filter_by(tuid=uid).scalar() is None:
                # we should save the user in user_data dict
                from_user = update.message.from_user
                user = User(tuid=uid, first_name=from_user.first_name, last_name=from_user.last_name)
                user_data['user'] = user
                # also save the user in DB
                session.add(user)
                session.commit()
            # but if the user is saved in DB
            else:
                # we should load the user to user_data dict
                user = session.query(User).filter_by(tuid=uid).scalar()
                user_data['user'] = user
            # create an empty cart for the user
            user_data["cart"] = Cart()
            user_data["prev_delivery_addr"] = []
            # welcome, pathetic user
            text = texts.welcome_user
        # if user is saved in user_data dict we have nothing to do but to welcome him again
        else:
            text = texts.welcome_again_user
        keyboard = main_kbd_user
        next_state = "MAIN_MENU_U"
    return ans(text=text, keyboard=keyboard, next_state=next_state)(bot, update)


def got_contact(bot, update, user_data=None):
    uid = update.message.from_user.id
    if user_data and update.message.contact:
        phone = update.message.contact.phone_number
        user_data['phone'] = phone
        user = session.query(User).filter_by(tuid=uid).scalar()
        user.phone = phone
        session.commit()
    return ans(text=texts.delivery_methods, keyboard=delivery_methods_kbd, next_state="DELIVERY_U")(bot, update)


def no_contact(bot, update):
    uid = update.message.from_user.id
    bot.sendChatAction(uid, action=typing)
    bot.sendSticker(uid, sticker=texts.sticker)
    bot.sendMessage(uid, text=texts.contact_err, parse_mode="HTML", reply_markup=kbd(send_contact_kbd))


def order_confirm(bot, update, user_data):
    answer = update.message.text
    keyboard = main_kbd_user
    next_state = "MAIN_MENU_U"
    # delivery:
    if "delivery_addr" in user_data:
        dtime = correct_time(answer)
        if not dtime:
            text = texts.wrong_time_format
            keyboard = None
            next_state = None
        else:
            user_data["delivery_time"] = dtime
            addr = user_data["delivery_addr"]
            ddate = user_data["delivery_date"]
            # dtime = user_data["delivery_time"]
            cart = user_data["cart"]
            order_json = cart.json_repr()
            new_order = Order(addr=addr, ddate=ddate, dtime=dtime, order=order_json)
            user = user_data['user']
            user.uorders.append(new_order)
            session.commit()
            # TODO: save delivery_addr and suggest it next time
            user_data["prev_delivery_addr"].append(addr)
            user_data["cart"] = Cart()
            del user_data["delivery_addr"]
            del user_data["delivery_date"]
            del user_data["delivery_time"]
            text = texts.delivery_confirmation % (addr, ddate, dtime, cart.total)
    # pickup:
    else:
        pickup_point = answer
        cart = user_data["cart"]
        order_json = cart.json_repr()
        new_order = Order(pickup=pickup_point, order=order_json)
        user = user_data['user']
        user.uorders.append(new_order)
        session.commit()
        text = texts.pickup_confirmation % (answer, cart.total)
        user_data["cart"] = Cart()
    return ans(text=text, keyboard=keyboard, next_state=next_state)(bot, update)


def orders_admin(bot, update):
    return ans(texts.orders_sort, keyboard=orders_sort_kbd, next_state="ORDERS_SORT_A")(bot, update)


def show_active_orders(bot, update, user_data):
    orders = session.query(Order).filter(Order.status != texts.order_status_completed)
    if orders.all():
        user_data["selected_orders"] = orders
        text = texts.select_order
        keyboard = [[order.full_label()] for order in orders]
        next_state = "ORDER_PROCESS_A"
    else:
        text = texts.no_selected_order
        keyboard = orders_sort_kbd
        next_state = None
    return ans(text=text, keyboard=keyboard, next_state=next_state)(bot, update)


def show_date_orders(bot, update, user_data):
    answer = update.message.text
    try:
        day, month, year = map(lambda x: int(x), answer.split(sep="."))
        date = datetime.date(year, month, day)
    except ValueError:
        text = texts.wrong_date_format
        keyboard = None  # orders_sort_kbd
        next_state = None
    else:
        orders = session.query(Order).filter(Order.ddate == date)
        if orders.all():
            user_data["selected_orders"] = orders
            text = texts.select_order
            keyboard = [[order.full_label()] for order in orders]
            next_state = "ORDER_PROCESS_A"
        else:
            text = texts.no_selected_order
            keyboard = orders_sort_kbd
            next_state = None
    return ans(text=text, keyboard=keyboard, next_state=next_state)(bot, update)


def show_archive(bot, update, user_data):
    orders = session.query(Order).filter(Order.status == texts.order_status_completed)
    if orders.all():
        user_data["selected_orders"] = orders
        text = texts.select_order
        keyboard = [[order.full_label()] for order in orders]
        next_state = "ORDER_PROCESS_A"
    else:
        text = texts.no_selected_order
        keyboard = orders_sort_kbd
        next_state = None
    return ans(text=text, keyboard=keyboard, next_state=next_state)(bot, update)


def process_order_admin(bot, update, user_data):
    answer = update.message.text
    for order in user_data["selected_orders"]:
        if order.full_label == answer:
            break
    if order.status != texts.order_status_completed:
        inlinekeyboard = edit_order_ikbd
        user_data["selected_order"] = order
    else:
        inlinekeyboard = None
    ans(text=str(order), inlinekeyboard=inlinekeyboard)(bot, update)


def change_order_status(bot, update, user_data):
    answer = update.message.text
    if answer not in flatten(order_status_kbd):
        return ans(text=texts.status_prompt, keyboard=order_status_kbd)(bot, update)
    else:
        if answer == texts.main_menu_btn:
            # this if statement isn't necessary
            return ans(text=texts.in_main_menu, keyboard=main_kbd_admin)(bot, update)
        else:
            # perform status update
            order = user_data["selected_order"]
            order.status = answer
            session.commit()
            # inform user
            bot.sendMessage(order.uid, text=(texts.alarm_status_updated % (str(order.timestamp.strftime(texts.dt_format)), answer)), parse_mode="HTML")
            # answer to admin
            return ans(text=texts.status_updated, keyboard=main_kbd_admin, next_state="MAIN_MENU_A")(bot, update)


def edit_admin(bot, update):
    uid = update.message.from_user.id
    bot.sendChatAction(uid, action=typing)
    bot.sendMessage(update.message.chat_id, text='edit', parse_mode="HTML", reply_markup=kbd(main_kbd_user))


def pie(data, labels, title=None):
    # TODO: cache results
    colors = ['lightskyblue', 'gold', 'lightcoral', 'yellowgreen']
    plt.xkcd()
    patches, _, _ = plt.pie(data, colors=colors, autopct='%1.1f%%', shadow=False, startangle=140)
    plt.legend(patches, labels, loc=(0.15, -0.30), prop={'family': 'Comic Sans MS'})
    plt.axis('equal')
    if title:
        plt.title(title, fontsize=24, position=(0.5, 1.1), family="Comic Sans MS")
    buf = io.BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight')
    plt.clf()
    buf.seek(0)
    return buf


def bar(data, labels, title=None):
    OY = data
    OX = list(range(len(OY)))
    width = .35
    ind = OX
    plt.xkcd()
    plt.bar(ind, OY, width=width)
    plt.xticks([i + width / 2 for i in ind], labels)
    xlocs, xlabels = plt.xticks()
    plt.setp(xlabels, rotation=90)
    plt.ylim([0, max(data)+1])
    if title:
        plt.title(title, fontsize=24, position=(0.5, 1.1), family="Comic Sans MS")
    buf = io.BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight')
    plt.clf()
    buf.seek(0)
    return buf


def static_stat_admin(bot, update):
    days = 30
    bot.sendChatAction(owner_id, action=telegram.ChatAction.UPLOAD_PHOTO, timeout=10)
    t_now = now()
    total_orders = session.query(Order).filter(Order.timestamp > t_now - datetime.timedelta(days=days)).count()
    completed_orders = session.query(Order).\
        filter(Order.timestamp > t_now - datetime.timedelta(days=days),
               Order.status != texts.order_status_completed).count()

    labels = ['завершеные', 'незавершенные']
    data = [total_orders-completed_orders, completed_orders]
    chart = pie(data, labels, title=texts.pie_title % days)
    bot.sendPhoto(chat_id=owner_id, photo=chart)
    chart.close()


def dynamic_stat_admin(bot, update):
    bot.sendChatAction(owner_id, action=telegram.ChatAction.UPLOAD_PHOTO, timeout=10)
    days = 30
    gs = 5  # group size: 5 days in a group
    n = int(days/gs)
    t_now = now()
    data = session.query(User.reg).filter(User.reg > t_now - datetime.timedelta(days=days)).all()
    data = [d[0] for d in data]
    data_dict = OrderedDict([(day, 0) for day in range(days)])
    for reg_date in data:
        dt = t_now - reg_date
        data_dict[dt.days] += 1
    grouped_data = OrderedDict([(g, 0) for g in range(n)])
    for g in range(n):
        grouped_data[g] = sum(data_dict[k] for k in range(g*gs, (g+1)*gs))
    labels = []
    for i in range(n):
        d1 = t_now - datetime.timedelta((0+i)*gs)
        d2 = d1 + datetime.timedelta(days=gs)
        labels.append(d1.strftime("%d.%m-")+d2.strftime("%d.%m"))
    labels.reverse()
    data = list(reversed(grouped_data.values()))
    bot.sendPhoto(chat_id=owner_id, photo=bar(data, labels, title=texts.new_users_plot_title))


def info_admin(bot, update):
    uid = update.message.from_user.id
    bot.sendChatAction(uid, action=typing)
    bot.sendMessage(update.message.chat_id, text=texts.info_admin, parse_mode="HTML", reply_markup=kbd(main_kbd_user))


def catalog_user(bot, update):
    return ans(text=texts.select_category, keyboard=catalog.categories_kbd + [[texts.main_menu_btn]], next_state="CATALOG")(bot, update)


def catalog_item(bot, update, user_data=None, text=None, inlinekeyboard=None, next_state=None, subcat=None):
    # TODO: Hide prev inline kbd
    if subcat is not None:
        user_data["scroll"] = subcat.copy()
    else:
        subcat = user_data["scroll"]
    if text is None:
        text = str(subcat[0])
    if inlinekeyboard is None:
        inlinekeyboard = catalog_ikbd
    return ans(text=text, inlinekeyboard=inlinekeyboard, next_state=next_state)(bot, update)


def cart_user(bot, update, user_data):
    uid = update.message.from_user.id
    cart = user_data["cart"]

    if cart:
        ans(text=texts.cart_welcome, keyboard=main_kbd_user)(bot, update)
        msgs = []
        for item in user_data["cart"].str_repr():
            bot.sendChatAction(uid, action=typing)
            msgs.append(bot.sendMessage(uid, text=item, parse_mode="HTML", reply_markup=ik(cart_item_ikbd)))
        user_data["cart_map"] = [msg.message_id for msg in msgs]
        user_data["cart_sum"] = bot.sendMessage(uid, text=texts.cart_sum % (len(cart), cart.total),
                                                reply_markup=ik(cart_sum_ikbd), parse_mode="HTML").message_id
    else:
        ans(text=texts.empty_cart, keyboard=main_kbd_user)(bot, update)
    return "MAIN_MENU_U"


def orders_user(bot, update, user_data):
    uid = update.message.from_user.id
    bot.sendChatAction(uid, action=typing)
    user_orders = session.query(Order).filter_by(uid=uid).all()
    if len(user_orders) > 0:
        user_orders.sort(key=lambda x: x.timestamp, reverse=True)
        user_data["user_orders"] = user_orders
        keyboard = [[str(order.timestamp.strftime(texts.dt_format))] for order in user_orders] + [[texts.main_menu_btn]]
        text = texts.select_order
        next_state = "ORDERS_U"
    else:
        text = texts.no_orders
        keyboard = main_kbd_user
        next_state = "MAIN_MENU_U"
    return ans(text=text, keyboard=keyboard, next_state=next_state)(bot, update)


def order_action(bot, update, user_data):
    uid = update.message.from_user.id
    bot.sendChatAction(uid, action=typing)
    user_orders = user_data["user_orders"]
    answer = update.message.text
    for order in user_orders:
        if order.timestamp.strftime(texts.dt_format) == answer:
            break
    return ans(text=str(order), keyboard=main_kbd_user, next_state="MAIN_MENU_U")(bot, update)


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
    try:
        scroll = user_data["scroll"]
        cart = user_data["cart"]
    except KeyError:
        pass

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
        cur = scroll.get_current()
        bot.sendPhoto(chat_id=chat_id, photo=cur.img, caption=cur.description, reply_markup=kbd(to_item_list_kbd))
        catalog_item(bot, update, user_data)
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
        index = user_data["cart_map"].index(message_id)
        del_item = cart[index]
        if cart[del_item] > 1:
            cart -= del_item
            bot.editMessageText(text=cart.str_repr()[index], chat_id=chat_id, message_id=message_id,
                                reply_markup=ik(cart_item_ikbd), parse_mode="HTML")
            bot.editMessageText(text=texts.cart_sum % (len(cart), cart.total), chat_id=chat_id,
                                message_id=user_data["cart_sum"],
                                reply_markup=ik(cart_sum_ikbd), parse_mode="HTML")
            bot.answerCallbackQuery(callback_query_id=cqid)
        else:
            bot.answerCallbackQuery(text=texts.cart_min_q, callback_query_id=cqid)

    elif act == "cart+1":
        index = user_data["cart_map"].index(message_id)
        add_item = cart[index]
        if cart[add_item] + 1 <= add_item.stock:
            cart += add_item
            bot.editMessageText(text=cart.str_repr()[index], chat_id=chat_id, message_id=message_id,
                                reply_markup=ik(cart_item_ikbd), parse_mode="HTML")
            bot.editMessageText(text=texts.cart_sum % (len(cart), cart.total), chat_id=chat_id,
                                message_id=user_data["cart_sum"],
                                reply_markup=ik(cart_sum_ikbd), parse_mode="HTML")
            bot.answerCallbackQuery(callback_query_id=cqid)
        else:
            bot.answerCallbackQuery(text=texts.not_enough_in_stock, callback_query_id=cqid)

    elif act == "del_all":
        for mid in user_data["cart_map"] + [user_data["cart_sum"]]:
            bot.editMessageText(text=texts.cart_item_deleted, chat_id=chat_id, message_id=mid, parse_mode="HTML")
        bot.answerCallbackQuery(callback_query_id=cqid)
        user_data["cart"] = Cart()
        del user_data["cart_map"]
        del user_data["cart_sum"]

    elif act == "confirm_all":
        bot.answerCallbackQuery(callback_query_id=cqid)
        if "phone" not in user_data:
            bot.sendMessage(uid, text=texts.ask_contact, parse_mode="HTML",
                            reply_markup=kbd(send_contact_kbd + [[texts.main_menu_btn]]))
            return "CHECK_CONTACT"
        else:
            bot.sendMessage(uid, text=texts.delivery_methods, reply_markup=kbd(delivery_methods_kbd), parse_mode="HTML")
            return "DELIVERY_U"

    elif act == "edit_order_status":
        bot.answerCallbackQuery(callback_query_id=cqid)
        bot.sendMessage(uid, text=texts.status_prompt, reply_markup=kbd(order_status_kbd), parse_mode="HTML")
        return "EDIT_STATUS"


def error(bot, update, err):
    logger.warn('Update "%s" caused error "%s"' % (update, err))


def load_state():
    try:
        sf = open(session_file, mode='rb')
    except IOError:
        from collections import defaultdict
        return dict(), defaultdict(dict)
    else:
        conversations, user_data = pickle.load(sf)
        sf.close()
        return conversations, user_data


def save_state(conversations, user_data):
    with open(session_file, mode='wb') as cf:
        pickle.dump((conversations, user_data), cf)


def load_data():
    pass


def save_data():
    pass


def main():
    updater = Updater(telegram_token)
    # Get the dispatcher to register handlers
    dp = updater.dispatcher

    cqh = telegram.ext.CallbackQueryHandler(inline, pass_user_data=True)

    states = {
        "CHECK_CONTACT": [MessageHandler(Filters.contact, got_contact, pass_user_data=True),
                          MessageHandler(Filters.text, no_contact)],

        "MAIN_MENU_A": [RegexHandler(texts.orders_btn_admin, orders_admin),
                        RegexHandler(texts.edit_btn_admin, edit_admin),
                        RegexHandler(texts.stat_btn_admin, ans(text=texts.stat_type, keyboard=stat_type_kbd, next_state="STAT")),
                        RegexHandler(texts.info_btn_admin, info_admin)],

        "STAT": [RegexHandler(texts.static_stat_btn, static_stat_admin),
                 RegexHandler(texts.dynamic_stat_btn, dynamic_stat_admin)],

        "MAIN_MENU_U": [RegexHandler(texts.catalog_btn_user, catalog_user),
                        RegexHandler(texts.cart_btn_user, cart_user, pass_user_data=True),
                        RegexHandler(texts.orders_btn_user, orders_user, pass_user_data=True),
                        RegexHandler(texts.info_btn_user, info_user)],

        "CATALOG": [
            RegexHandler(btn, ans(text=texts.select_subcategory % btn,
                                  keyboard=catalog.subcat_kbd[btn] + [[texts.main_menu_btn]],
                                  next_state="CATALOG_" + btn))
            for btn in flatten(catalog.categories_kbd)],

        "TO_CART_DONE": [RegexHandler(texts.confirm_order_btn, cart_user, pass_user_data=True),
                         RegexHandler(texts.to_cat_btn, catalog_user)],

        "DELIVERY_U": [RegexHandler(texts.delivery_carrier_btn, ans(text=texts.delivery_addr_input,
                                                                    next_state="DELIVERY_ADDR")),
                       RegexHandler(texts.delivery_pickup_btn, ans(text=texts.delivery_pickup_input,
                                                                   keyboard=pickup_points,
                                                                   next_state="PICKUP_POINT")),
                       ],

        "DELIVERY_ADDR": [MessageHandler(Filters.text, saving_ans(text=texts.delivery_date_input, name="delivery_addr",
                                                                  next_state="DELIVERY_DATE"), pass_user_data=True)],

        "DELIVERY_DATE": [MessageHandler(Filters.text, saving_ans(text=texts.delivery_time_input, name="delivery_date",
                                                                  next_state="DELIVERY_TIME", checker=correct_date,
                                                                  error_text=texts.wrong_date_format),
                                         pass_user_data=True)],

        "DELIVERY_TIME": [MessageHandler(Filters.text, order_confirm, pass_user_data=True)],

        "PICKUP_POINT": [MessageHandler(Filters.text, order_confirm, pass_user_data=True)],

        "ORDERS_U": [MessageHandler(Filters.text, order_action, pass_user_data=True)],

        "ORDERS_SORT_A": [RegexHandler(texts.active_orders_btn, show_active_orders, pass_user_data=True),
                          RegexHandler(texts.date_orders_btn, ans(texts.date_input, next_state="DATE_INPUT_A")),
                          RegexHandler(texts.archive_orders_btn, show_archive, pass_user_data=True)],

        "DATE_INPUT_A": [MessageHandler(Filters.text, show_date_orders, pass_user_data=True)],

        "ORDER_PROCESS_A": [MessageHandler(Filters.text, process_order_admin, pass_user_data=True)],

        "EDIT_STATUS": [RegexHandler(texts.cancel_status_input_btn,
                                     ans(text=texts.status_input_cancelled,
                                         keyboard=main_kbd_admin, next_state="MAIN_MENU_A")),
                        MessageHandler(Filters.text, change_order_status, pass_user_data=True)
                        ],

    }

    states["DATE_INPUT_A"] = states["ORDERS_SORT_A"] + states["DATE_INPUT_A"]

    for cat in flatten(catalog.categories_kbd):
        states["CATALOG_" + cat] = [RegexHandler(btn,
                                                 lambda bot, update, user_data, cat=cat, btn=btn:
                                                 catalog_item(bot, update, user_data=user_data,
                                                              text=str(catalog[cat][btn][0]), subcat=catalog[cat][btn]),
                                                 pass_user_data=True)
                                    for btn in flatten(catalog.subcat_kbd[cat])]

    command_handlers = [CommandHandler('start', start, pass_user_data=True), ]
    back_to_list_handler = [RegexHandler(texts.to_item_list_btn, catalog_item, pass_user_data=True)]
    main_menu_handler = [RegexHandler(texts.main_menu_btn,
                                       ans(text=texts.main_menu_btn, keyboard=main_kbd_user, next_state="MAIN_MENU_U"))]

    # inline buttons and slash-commands must be handled from any chat state
    states = {k: main_menu_handler + command_handlers + [cqh] + back_to_list_handler + v for k, v in states.items()}

    # Add conversation handler with the states
    conversation_handler = ConversationHandler(entry_points=command_handlers, states=states, fallbacks=[])

    # load user data and conversations states from file
    conversation_handler.conversations, dp.user_data = load_state()
    dp.add_handler(conversation_handler)

    # log all errors
    dp.add_error_handler(error)

    # Start the Bot
    updater.start_polling()

    # Run the bot until the you presses Ctrl-C or the process receives SIGINT,
    # SIGTERM or SIGABRT. This should be used most of the time, since
    # start_polling() is non-blocking and will stop the bot gracefully.
    updater.idle()

    # save user data and conversations states to file
    save_state(conversation_handler.conversations, dp.user_data)


if __name__ == '__main__':
    main()
