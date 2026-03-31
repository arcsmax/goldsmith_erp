"""Factory for Order model test data."""
import factory
from datetime import datetime, timedelta
from goldsmith_erp.db.models import Order, OrderStatusEnum


class OrderFactory(factory.Factory):
    class Meta:
        model = Order

    title = factory.Sequence(lambda n: f"Auftrag {n}")
    description = factory.Faker("sentence", locale="de_DE")
    status = OrderStatusEnum.NEW
    customer_id = None
    price = factory.Faker("pydecimal", left_digits=4, right_digits=2, positive=True)
    deadline = factory.LazyFunction(lambda: datetime.utcnow() + timedelta(days=14))
