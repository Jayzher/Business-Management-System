from django.urls import path
from pos import views

urlpatterns = [
    # Registers
    path('registers/', views.register_list_view, name='pos_register_list'),
    path('registers/create/', views.register_create_view, name='pos_register_create'),
    path('registers/<int:pk>/edit/', views.register_edit_view, name='pos_register_edit'),
    path('registers/<int:pk>/delete/', views.register_delete_view, name='pos_register_delete'),
    # Shifts
    path('shifts/', views.shift_list_view, name='pos_shift_list'),
    path('shifts/open/', views.shift_open_view, name='pos_shift_open'),
    path('shifts/<int:pk>/close/', views.shift_close_view, name='pos_shift_close'),
    path('shifts/<int:pk>/summary/', views.shift_summary_view, name='pos_shift_summary'),
    # Terminal
    path('terminal/<int:shift_id>/', views.terminal_view, name='pos_terminal'),
    path('terminal/<int:shift_id>/new-sale/', views.terminal_new_sale, name='pos_terminal_new_sale'),
    path('terminal/sale/<int:sale_id>/add-line/', views.terminal_add_line, name='pos_terminal_add_line'),
    path('terminal/line/<int:line_id>/remove/', views.terminal_remove_line, name='pos_terminal_remove_line'),
    path('terminal/line/<int:line_id>/update-qty/', views.terminal_update_qty, name='pos_terminal_update_qty'),
    path('terminal/sale/<int:sale_id>/checkout/', views.terminal_checkout, name='pos_terminal_checkout'),
    # Receipts
    path('receipts/', views.receipt_list_view, name='pos_receipt_list'),
    path('receipts/<int:pk>/', views.receipt_detail_view, name='pos_receipt_detail'),
    # Refunds
    path('receipts/<int:sale_pk>/refund/', views.refund_create_view, name='pos_refund_create'),
]
