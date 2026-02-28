import io
import qrcode
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.core.files.base import ContentFile
from rest_framework import viewsets, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from qr.models import QRCodeTag, ScanEvent
from qr.serializers import QRCodeTagSerializer, ScanEventSerializer, QRScanRequestSerializer
from audit.models import AuditLog


def _generate_qr_image(data_str):
    """Generate a QR code image and return as ContentFile."""
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(data_str)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    return ContentFile(buf.read(), name=f"{data_str}.png")


# ── API Views ──────────────────────────────────────────────────────────────

class QRCodeTagViewSet(viewsets.ModelViewSet):
    queryset = QRCodeTag.objects.select_related('item', 'location').all()
    serializer_class = QRCodeTagSerializer
    filterset_fields = ['item', 'is_active', 'printed']
    search_fields = ['item__code', 'item__name', 'batch_number', 'serial_number']


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def generate_qr(request):
    """Generate QR code(s) for items. Accepts single or bulk."""
    items_data = request.data.get('items', [])
    if not items_data:
        item_id = request.data.get('item_id')
        if item_id:
            items_data = [{'item_id': item_id}]
    if not items_data:
        return Response({'error': 'Provide item_id or items list.'}, status=status.HTTP_400_BAD_REQUEST)

    from catalog.models import Item
    created = []
    for entry in items_data:
        try:
            item = Item.objects.get(pk=entry.get('item_id'))
        except Item.DoesNotExist:
            continue
        tag = QRCodeTag.objects.create(
            item=item,
            batch_number=entry.get('batch_number', ''),
            serial_number=entry.get('serial_number', ''),
        )
        img_file = _generate_qr_image(str(tag.qr_uid))
        tag.image.save(f"qr_{tag.qr_uid}.png", img_file, save=True)
        created.append(QRCodeTagSerializer(tag).data)

    return Response({'created': len(created), 'tags': created}, status=status.HTTP_201_CREATED)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def qr_lookup(request, uid):
    """Look up a QR code by its UUID."""
    tag = get_object_or_404(QRCodeTag, qr_uid=uid)
    serializer = QRCodeTagSerializer(tag)
    return Response(serializer.data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def qr_scan(request):
    """Process a QR scan action."""
    ser = QRScanRequestSerializer(data=request.data)
    ser.is_valid(raise_exception=True)
    data = ser.validated_data

    tag = get_object_or_404(QRCodeTag, qr_uid=data['qr_uid'])

    from warehouses.models import Location
    location = None
    if data.get('location_id'):
        location = get_object_or_404(Location, pk=data['location_id'])

    event = ScanEvent.objects.create(
        qr_tag=tag,
        action=data['action'],
        location=location,
        qty=data.get('qty'),
        scanned_by=request.user,
        notes=data.get('notes', ''),
    )

    AuditLog.objects.create(
        user=request.user,
        action='SCAN',
        model_name='QRCodeTag',
        object_id=tag.pk,
        object_repr=str(tag),
        changes={'action': data['action'], 'location': str(location)},
    )

    result = {
        'event_id': event.pk,
        'qr_uid': str(tag.qr_uid),
        'item_code': tag.item.code,
        'item_name': tag.item.name,
        'item_id': tag.item.pk,
        'action': data['action'],
        'is_serial': bool(tag.serial_number),
    }

    # POS integration: if register_id provided, return availability info
    register_id = request.data.get('register_id')
    if register_id:
        from pos.models import POSRegister
        from inventory.models import StockBalance
        try:
            reg = POSRegister.objects.select_related('warehouse').get(pk=register_id)
            balances = StockBalance.objects.filter(
                item=tag.item,
                location__warehouse=reg.warehouse,
                qty_on_hand__gt=0,
            ).select_related('location').values(
                'location__id', 'location__code', 'qty_on_hand', 'qty_reserved',
            )
            result['available_locations'] = list(balances)
            result['total_available'] = sum(
                b['qty_on_hand'] - b['qty_reserved'] for b in balances
            )
        except POSRegister.DoesNotExist:
            pass

    return Response(result)


# ── Template Views ─────────────────────────────────────────────────────────

@login_required
def qr_list_view(request):
    tags = QRCodeTag.objects.select_related('item', 'location').all()[:100]
    return render(request, 'qr/qr_list.html', {'tags': tags})


@login_required
def qr_scan_view(request):
    return render(request, 'qr/qr_scan.html')


@login_required
def qr_print_view(request):
    tag_ids = request.GET.getlist('ids')
    if tag_ids:
        tags = QRCodeTag.objects.filter(pk__in=tag_ids).select_related('item')
    else:
        tags = QRCodeTag.objects.filter(printed=False).select_related('item')[:50]
    return render(request, 'qr/qr_print.html', {'tags': tags})
