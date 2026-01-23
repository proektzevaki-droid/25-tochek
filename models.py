"""
Модели базы данных для системы управления заказами.

Этот модуль содержит все SQLAlchemy модели, используемые в приложении:
- Point: точки продаж
- Order: заказы
- OrderItem: элементы заказов
- Supplier: поставщики
- Product: товары
- SupplierProduct: связь поставщиков с товарами
- SupplierRule: правила для поставщиков
- History: история обработки файлов
- HistoryOrderItem: элементы заказов в истории
"""

from datetime import datetime, timezone, timedelta

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from database import Base


def moscow_now():
    """Возвращает текущее время в московском часовом поясе (UTC+3)"""
    moscow_tz = timezone(timedelta(hours=3))
    return datetime.now(moscow_tz).replace(tzinfo=None)


class Point(Base):
    """Модель точки продаж.

    Хранит информацию о точках продаж, включая адрес, владельца и Telegram ID.
    Поддерживает мягкое удаление через флаг is_deleted.
    """

    __tablename__ = "points"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True, nullable=True, comment="Название точки продаж")
    address = Column(String, nullable=True, comment="Адрес точки продаж")
    owner = Column(String, nullable=True, comment="Владелец точки")
    idTg = Column(String, nullable=False, comment="Telegram ID точки")
    manager_telegram_id = Column(String, nullable=True, comment="Telegram ID управляющих (можно несколько через запятую)")
    note = Column(Text, nullable=True, comment="Примечание")
    is_deleted = Column(Boolean, default=False, comment="Флаг мягкого удаления")


class Order(Base):
    """Модель заказа.

    Хранит информацию о заказах, включая связь с точкой продаж,
    статус заказа, данные о клиенте из Telegram и флаги обработки.
    """

    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    point_id = Column(Integer, ForeignKey("points.id"), nullable=True, comment="ID точки продаж")
    created_at = Column(DateTime, default=moscow_now, comment="Дата и время создания заказа")
    status = Column(String, default="new", comment="Статус заказа")
    tg_name = Column(String, default="", comment="Имя клиента из Telegram")
    tg_username = Column(String, default="", comment="Username клиента из Telegram")
    sent_to_supplier = Column(Boolean, default=False, comment="Флаг отправки заказа поставщику")
    is_closed = Column(
        Boolean,
        default=False,
        comment="Статус закрытия заказа (в MVP заводим, но в логике не используем)",
    )

    # Relationships
    items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")
    point = relationship("Point")


class OrderItem(Base):
    """Модель элемента заказа.

    Хранит информацию об отдельных товарах в заказе,
    включая тип, подтип, название и количество.
    """

    __tablename__ = "order_items"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False, comment="ID заказа")
    product_id = Column(Integer, ForeignKey("product.id"), nullable=True, comment="ID товара")
    suppliers_id = Column(Integer, ForeignKey("suppliers.id"), nullable=True, comment="ID поставщика")
    type = Column(String, nullable=True, comment="Тип товара")
    subtype = Column(String, nullable=True, comment="Подтип товара")
    name = Column(String, nullable=True, comment="Название товара")
    count = Column(Float, nullable=True, comment="Количество товара")
    is_sent_to_supplier = Column(
        Boolean,
        default=False,
        comment="Статус отправки товара поставщику",
    )
    is_sending_to_supplier = Column(
        Boolean,
        default=False,
        comment="Статус процесса отправки товара поставщику (ожидание callback от n8n)",
    )

    # Relationships
    order = relationship("Order", back_populates="items")
    product = relationship("Product")
    supplier = relationship("Supplier")


class Supplier(Base):
    """Модель поставщика.

    Хранит информацию о поставщиках, включая контактные данные:
    название, email и Telegram.
    """

    __tablename__ = "suppliers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, comment="Название поставщика")
    email = Column(String, nullable=True, comment="Email поставщика (с валидацией формата)")
    telegram = Column(String, nullable=True, comment="Telegram (логин или ID)")
    telegram_id = Column(Integer, nullable=True, comment="Telegram ID пользователя (числовой ID)")

    # Relationships
    products = relationship("SupplierProduct", back_populates="supplier", cascade="all, delete-orphan")
    rules = relationship("SupplierRule", back_populates="supplier", cascade="all, delete-orphan")


class Product(Base):
    """Модель товара.

    Хранит базовую информацию о товарах: название, единицу измерения и вид товара.
    """

    __tablename__ = "product"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, comment="Название товара")
    unit = Column(String, nullable=True, comment="Единица измерения")
    product_type = Column(String, nullable=True, comment="Вид товара (категория)")


class SupplierProduct(Base):
    """Модель связи поставщика с товаром.

    Создает связь многие-ко-многим между поставщиками и товарами.
    Один поставщик может поставлять множество товаров,
    один товар может поставляться разными поставщиками.
    """

    __tablename__ = "supplier_products"

    id = Column(Integer, primary_key=True, index=True)
    supplier_id = Column(
        Integer,
        ForeignKey("suppliers.id"),
        nullable=False,
        comment="ID поставщика",
    )
    product_id = Column(
        Integer,
        ForeignKey("product.id"),
        nullable=False,
        comment="ID товара",
    )

    # Relationships
    supplier = relationship("Supplier", back_populates="products")
    product = relationship("Product")

    # Constraints
    __table_args__ = (
        UniqueConstraint("supplier_id", "product_id", name="uq_supplier_product"),
    )


class SupplierRule(Base):
    """Модель правила для поставщика.

    Хранит правила обработки заказов для конкретного поставщика.
    Правила содержат текст с маркерами [PRODUCT:id] для подстановки товаров.
    Поддерживает приоритет и активность правил.
    """

    __tablename__ = "supplier_rules"

    id = Column(Integer, primary_key=True, index=True)
    supplier_id = Column(
        Integer,
        ForeignKey("suppliers.id"),
        nullable=False,
        comment="ID поставщика",
    )
    rule_text = Column(
        Text,
        nullable=False,
        comment="Текст правила с маркерами [PRODUCT:id]",
    )
    priority = Column(
        Integer,
        default=100,
        comment="Приоритет правила (чем меньше, тем выше)",
    )
    is_active = Column(Boolean, default=True, comment="Активность правила")

    # Relationships
    supplier = relationship("Supplier", back_populates="rules")


class History(Base):
    """Модель истории обработки файлов.

    Хранит информацию о файлах, отправленных поставщикам,
    включая статус обработки (принята/отказана) и связи с заказами и поставщиками.
    """

    __tablename__ = "history"

    id = Column(Integer, primary_key=True, index=True)
    file_path = Column(String, nullable=False, comment="Путь к файлу")
    status = Column(String, default="отказана", comment="Статус обработки (принята/отказана)")
    created_at = Column(DateTime, default=moscow_now, comment="Дата и время создания записи")
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=True, comment="ID заказа")
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=True, comment="ID поставщика")

    # Relationships
    order = relationship("Order")
    supplier = relationship("Supplier")
    order_items = relationship("HistoryOrderItem", back_populates="history", cascade="all, delete-orphan")


class HistoryOrderItem(Base):
    """Модель связи истории с элементами заказа.

    Создает связь между записями истории и элементами заказов,
    позволяя отслеживать, какие товары были отправлены в каждом файле.
    """

    __tablename__ = "history_order_items"

    id = Column(Integer, primary_key=True, index=True)
    history_id = Column(
        Integer,
        ForeignKey("history.id"),
        nullable=False,
        comment="ID записи истории",
    )
    order_item_id = Column(
        Integer,
        ForeignKey("order_items.id"),
        nullable=False,
        comment="ID элемента заказа",
    )

    # Relationships
    history = relationship("History", back_populates="order_items")
    order_item = relationship("OrderItem")

    # Constraints
    __table_args__ = (
        UniqueConstraint("history_id", "order_item_id", name="uq_history_order_item"),
    )
