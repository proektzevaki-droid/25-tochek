from pydantic import BaseModel
from typing import List, Optional, Union
from datetime import datetime

# ---- Point ----
class PointBase(BaseModel):
    name: Optional[str] = None
    owner: Optional[str] = None
    idTg: str
    address: Optional[str] = None
    manager_telegram_id: Optional[str] = None
    note: Optional[str] = None

class PointCreate(PointBase):
    pass

class PointUpdate(BaseModel):
    """Схема для обновления точки - все поля опциональны"""
    name: Optional[str] = None
    owner: Optional[str] = None
    idTg: Optional[str] = None
    address: Optional[str] = None
    manager_telegram_id: Optional[str] = None
    note: Optional[str] = None

class Point(PointBase):
    id: int  # ID используется для операций, но не отображается в UI
    is_deleted: Optional[bool] = False
    class Config:
        from_attributes = True

# ---- OrderItem ----
class OrderItemBase(BaseModel):
    type: Optional[str] = None
    subtype: Optional[str] = None
    name: Optional[str] = None
    count: Optional[float] = None
    product_id: Optional[int] = None
    suppliers_id: Optional[int] = None
    unit: Optional[str] = None

class OrderItemCreate(OrderItemBase):
    pass

class OrderItem(OrderItemBase):
    id: int
    class Config:
        from_attributes = True

# ---- Order ----
class OrderBase(BaseModel):
    items: List[OrderItemCreate]
    point_id: Optional[int] = None
    tg_name: Optional[str] = ""
    tg_username: Optional[str] = ""

class OrderCreate(OrderBase):
    pass

class Order(OrderBase):
    id: int
    created_at: datetime
    status: str
    items: List[OrderItem]
    point: Optional[Point] = None

    class Config:
        from_attributes = True

class OrderCreateWithName(BaseModel):
    point_name: str  # вместо point_id
    tg_name: str
    tg_username: str
    items: List[OrderItemCreate]

# ---- Новые схемы для структуры запроса с массивом заказов ----
class OrderItemRequest(BaseModel):
    """Схема для элемента заказа из входящего запроса"""
    product_id: Union[str, int]  # Принимает строку или число
    product_type: str
    product_subtype: str
    product_name: str
    product_count: float
    product_unit: Optional[str] = None  # Единица измерения товара
    suppliers_id: Union[str, int]  # Принимает строку или число
    suppliers_name: str

class OrderRequest(BaseModel):
    """Схема для одного заказа из входящего запроса"""
    point_id: int
    tg_name: str
    tg_username: str
    point: Optional[str] = None  # название точки (не используется в БД, но может быть полезно)
    items: List[OrderItemRequest]
    text: Optional[str] = None  # текст заказа (не используется в БД)

# ---- Supplier ----
class SupplierBase(BaseModel):
    name: str
    email: Optional[str] = None
    telegram: Optional[str] = None
    telegram_id: Optional[int] = None

class SupplierCreate(SupplierBase):
    pass

class SupplierUpdate(BaseModel):
    """Схема для обновления поставщика - все поля опциональны"""
    name: Optional[str] = None
    email: Optional[str] = None
    telegram: Optional[str] = None
    telegram_id: Optional[int] = None

class SupplierProductInfo(BaseModel):
    """Информация о товаре поставщика"""
    id: int
    name: str
    unit: Optional[str] = None
    product_type: Optional[str] = None
    class Config:
        from_attributes = True

class Supplier(SupplierBase):
    id: int
    products: List[SupplierProductInfo] = []
    rules: List["SupplierRule"] = []
    class Config:
        from_attributes = True

class SupplierResponse(BaseModel):
    """Схема для ответа с информацией о поставщике (с has_telegram_id вместо telegram_id)"""
    id: int
    name: str
    email: Optional[str] = None
    telegram: Optional[str] = None
    has_telegram_id: bool  # Булево значение вместо telegram_id
    products: List[SupplierProductInfo] = []
    rules: List["SupplierRule"] = []
    class Config:
        from_attributes = True

class SupplierSimple(BaseModel):
    """Упрощенная схема поставщика - id, name и доступные способы связи"""
    id: int
    name: str
    available_contacts: List[str]  # Список доступных способов связи: ['email', 'telegram']
    class Config:
        from_attributes = True

# ---- History ----
class HistoryBase(BaseModel):
    file_path: str
    created_at: Optional[datetime] = None  # если нужно хранить дату создания

class HistoryCreate(HistoryBase):
    pass

class History(HistoryBase):
    id: int

    class Config:
        from_attributes = True

# ---- Product ----
class ProductBase(BaseModel):
    name: str
    unit: Optional[str] = None
    product_type: Optional[str] = None

class ProductCreate(ProductBase):
    pass

class ProductUpdate(BaseModel):
    """Схема для обновления товара - все поля опциональны"""
    name: Optional[str] = None
    unit: Optional[str] = None
    product_type: Optional[str] = None

class Product(ProductBase):
    id: int
    class Config:
        from_attributes = True

# ---- SupplierRule ----
class SupplierRuleBase(BaseModel):
    rule_text: str
    priority: Optional[int] = 100
    is_active: Optional[bool] = True

class SupplierRuleCreate(SupplierRuleBase):
    pass

class SupplierRuleUpdate(BaseModel):
    rule_text: Optional[str] = None
    priority: Optional[int] = None
    is_active: Optional[bool] = None

class SupplierRule(SupplierRuleBase):
    id: int
    supplier_id: int
    class Config:
        from_attributes = True