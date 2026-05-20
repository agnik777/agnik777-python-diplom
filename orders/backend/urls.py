# backend/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (UserRegistrationView, ConfirmEmailView,
                    UserLoginView, PartnerUpdate, ShopListView,
                    ShopCategoriesView, ProductSearchView, CartView,
                    CartItemDetailView, ProductDetailView, PhoneView,
                    ContactDetailView, OrderCreateView, OrderConfirmView,
                    OrderListView, OrderDetailView, ContactViewSet,
                    ShopPermissionUpdateView, ShopOrderListView,
                    LogoutView, AvatarViewSet, ProductImageViewSet,
                    SocialAuthCompleteView, SocialAuthErrorView,)
from .views_debug import SentryDebugView


router = DefaultRouter()
router.register(r'product-images', ProductImageViewSet,
                basename='product-image')

urlpatterns = [
    path('register/', UserRegistrationView.as_view(), name='register'),
    path('confirm-email/<str:token_key>/', ConfirmEmailView.as_view(),
         name='confirm-email'),
    path('login/', UserLoginView.as_view(), name='login'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('partner/update/', PartnerUpdate.as_view(),
         name='partner-update'),
    path('shops/', ShopListView.as_view(), name='shop-list'),
    path('shop/categories/', ShopCategoriesView.as_view(),
         name='shop-categories'),
    path('products/search/', ProductSearchView.as_view(),
         name='product-search'),
    path('cart/', CartView.as_view(), name='cart'),
    path('cart/items/<int:item_id>/', CartItemDetailView.as_view(),
         name='cart-item-detail'),
    path('products/<int:pk>/', ProductDetailView.as_view(),
         name='product-detail'),
    path('phone/', PhoneView.as_view(), name='phone'),
    path('contacts/', ContactViewSet.as_view(), name='contact-list'),
    path('contacts/<int:pk>/', ContactDetailView.as_view(),
         name='contact-detail'),
    path('orders/create/', OrderCreateView.as_view(),
         name='order-create'),
    path('orders/confirm/', OrderConfirmView.as_view(),
         name='order-confirm'),
    path('orders/', OrderListView.as_view(), name='order-list'),
    path('orders/<int:pk>/', OrderDetailView.as_view(),
         name='order-detail'),
    path('shops/<int:pk>/permission/',
         ShopPermissionUpdateView.as_view(),
         name='shop-permission-update'),
    path('shops/orders/', ShopOrderListView.as_view(),
         name='shop-order-list'),
    path('debug/sentry/', SentryDebugView.as_view(),
         name='debug-sentry'),

    path('avatar/', AvatarViewSet.as_view({'get': 'retrieve'}),
      name='avatar-detail'),
    path('avatar/upload/', AvatarViewSet.as_view({'post': 'upload'}),
         name='avatar-upload'),
    path('avatar/delete/',
         AvatarViewSet.as_view({'delete': 'delete_avatar'}),
         name='avatar-delete'),
    path('', include(router.urls)),
]

urlpatterns += [
    path('social-auth/complete/', SocialAuthCompleteView.as_view(),
         name='social-complete'),
    path('social-auth/error/', SocialAuthErrorView.as_view(),
         name='social-error'),
]
