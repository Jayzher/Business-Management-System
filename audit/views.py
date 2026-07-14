from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages

from audit.models import AuditLog, ManualLog
from accounts.decorators import write_denied_for_viewer


@login_required
def system_logs(request):
    """System logs page — data loaded via API."""
    return render(request, 'audit/system_logs.html')


@login_required
def manual_logs(request):
    """Manual logs page — data loaded via API."""
    return render(request, 'audit/manual_logs.html')


@login_required
@write_denied_for_viewer
def manual_log_create(request):
    """Create a new manual change log entry."""
    if request.method == 'POST':
        ManualLog.objects.create(
            user=request.user,
            action=request.POST.get('action', 'OTHER'),
            table_name=request.POST.get('table_name', '').strip(),
            record_id=request.POST.get('record_id', '').strip(),
            fields_changed=request.POST.get('fields_changed', '').strip(),
            old_value=request.POST.get('old_value', '').strip(),
            new_value=request.POST.get('new_value', '').strip(),
            reason=request.POST.get('reason', '').strip(),
            notes=request.POST.get('notes', '').strip(),
        )
        messages.success(request, 'Manual log entry created.')
        return redirect('audit:manual_logs')

    from django.apps import apps
    table_choices = sorted(set(
        m._meta.db_table for m in apps.get_models()
        if m._meta.app_label in (
            'catalog', 'inventory', 'procurement', 'sales', 'pos',
            'services', 'cashflow', 'core', 'accounts', 'pricing',
            'partners', 'warehouses', 'audit',
        )
    ))

    return render(request, 'audit/manual_log_form.html', {
        'action_choices': ManualLog.ACTION_CHOICES,
        'table_choices': table_choices,
    })


@login_required
def manual_log_detail(request, pk):
    """View a single manual log entry."""
    log = get_object_or_404(ManualLog, pk=pk)
    return render(request, 'audit/manual_log_detail.html', {'log': log})
