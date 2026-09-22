import factory
from factory.django import DjangoModelFactory

from apps.products.models import Category, Product


class CategoryFactory(DjangoModelFactory):
    class Meta:
        model = Category
        django_get_or_create = ("name",)

    name = factory.Sequence(lambda n: f"Categoria {n}")
    is_active = True


class ProductFactory(DjangoModelFactory):
    class Meta:
        model = Product

    name = factory.Sequence(lambda n: f"Produto {n}")
    description = "Descrição de teste"
    price = "79.90"
    stock = 10
    category = factory.SubFactory(CategoryFactory)
    is_active = True
    is_published = True
