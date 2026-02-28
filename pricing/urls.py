from django.urls import path
from pricing import views

urlpatterns = [
    path('price-lists/', views.price_list_list_view, name='price_list_list'),
    path('price-lists/create/', views.price_list_create_view, name='price_list_create'),
    path('price-lists/<int:pk>/edit/', views.price_list_edit_view, name='price_list_edit'),
    path('price-lists/<int:pk>/delete/', views.price_list_delete_view, name='price_list_delete'),
    path('discount-rules/', views.discount_rule_list_view, name='discount_rule_list'),
    path('discount-rules/create/', views.discount_rule_create_view, name='discount_rule_create'),
    path('discount-rules/<int:pk>/edit/', views.discount_rule_edit_view, name='discount_rule_edit'),
    path('discount-rules/<int:pk>/delete/', views.discount_rule_delete_view, name='discount_rule_delete'),
]
