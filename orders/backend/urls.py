from django.urls import path
from .views import (UserRegistrationView, ConfirmEmailView,
                    UserLoginView, PartnerUpdate, ShopListView, ShopCategoriesView, ProductSearchView)


urlpatterns = [
    path('register/', UserRegistrationView.as_view(), name='register'),
    path('confirm-email/<str:token_key>/', ConfirmEmailView.as_view(),
         name='confirm-email'),
    path('login/', UserLoginView.as_view(), name='login'),
    path('partner/update/', PartnerUpdate.as_view(), name='partner-update'),
    path('shops/', ShopListView.as_view(), name='shop-list'),
    path('shop/categories/', ShopCategoriesView.as_view(), name='shop-categories'),
    path('products/search/', ProductSearchView.as_view(), name='product-search'),
]
