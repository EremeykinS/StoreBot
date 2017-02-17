import json
from datetime import datetime, timedelta
from collections import OrderedDict

from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, ForeignKey, BigInteger, String, DateTime, Date, Time, JSON
from sqlalchemy.orm import relationship

import texts

__all__ = ["Base", "User", "Order", "Entity", "SubCat", "Catalog", "Cart", ]

Base = declarative_base()
now = datetime.now


class User(Base):
    __tablename__ = "users"
    tuid = Column(BigInteger, primary_key=True)
    reg = Column(DateTime, default=now)
    first_name = Column(String(127))
    last_name = Column(String(127))
    phone = Column(String(31))
    uorders = relationship("Order", back_populates="user")


class Order(Base):
    __tablename__ = "orders"
    oid = Column(BigInteger, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=now)
    addr = Column(String(127), default=None)
    pickup = Column(String(127), default=None)
    ddate = Column(Date)
    dtime = Column(Time)
    order = Column(JSON)
    upd = Column(DateTime, default=now, onupdate=now)
    status = Column(String(63))
    uid = Column(BigInteger, ForeignKey('users.tuid'))
    user = relationship("User", back_populates="uorders")

    def __init__(self, **kwargs):
        kwargs.update(
            dict(status=kwargs.get("status", texts.default_order_status),
                 ddate=kwargs.get("ddate", now() + timedelta(days=2)),
                 dtime=kwargs.get("dtime", "12:00")))
        super().__init__(**kwargs)

    def __str__(self):
        content = ""
        _order = json.loads(self.order, object_pairs_hook=dict)
        for e in _order:
            content += e['description'] + " (%d), " % e['q']
        total = sum(e['price']*e['q'] for e in _order)
        return texts.order_info % (content, total, self.status, self.upd.strftime(texts.dt_format))

    def full_label(self):
        return self.timestamp.strftime(texts.dt_format) + " [" + self.user.first_name + " " + self.user.last_name + "]"


class Entity:
    def __init__(self, entity_dict=None):
        if entity_dict is None:
            self._dict = OrderedDict()
        else:
            self._dict = OrderedDict(entity_dict)
            for key, value in self._dict.items():
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
        return type(self).__name__ + "(" + (", ".join("%s='%s'" % (k, v) for k, v in self._dict.items())) + ")"


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
        return sum(p.price * q for p, q in self.items.items())

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
        return [str(i + 1) + ". " + (texts.cart_items % (p.description, q, p.price, p.price * q))
                for i, (p, q) in enumerate(self.items.items())]

    def json_repr(self):
        tl = []
        for e, q in self.items.items():
            new_e = Entity(e._dict)
            new_e._dict["q"] = q
            tl.append(new_e._dict)
        return json.dumps(tl)

    @classmethod
    def from_json(cls, json_string):
        cart = cls()
        d = json.loads(json_string, object_pairs_hook=OrderedDict)
        for e in d:
            q = e.q
            del e.q
            restored_e = Entity(e)
            cart.add(restored_e, q)
        return cart

    def __getitem__(self, item):
        try:
            it = iter(self.items.keys())
            for i in range(item + 1):
                e = next(it)
            return e
        except TypeError:
            return self.items[item] if item in self.items else 0

    def __delitem__(self, key):
        try:
            it = iter(self.items.keys())
            for i in range(key + 1):
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
