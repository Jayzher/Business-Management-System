"""
Middleware for modal form handling.
When a request includes `_modal=1` (GET or POST) and the view returns a redirect
(successful form save / delete), the middleware intercepts it and returns JSON
so the client-side modal JS can close the modal, show a toast, and refresh.

Also intercepts non-redirect POST responses that carry Django messages (e.g.
delete views that re-render with an error) and returns JSON so the modal JS
can display the error toast without a full page reload.
"""
from django.http import JsonResponse
from django.contrib.messages import get_messages


class ModalFormMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        is_modal = '_modal' in request.GET or '_modal' in request.POST
        request._is_modal = is_modal

        response = self.get_response(request)

        if not is_modal:
            return response

        # Intercept redirects (successful form save / delete)
        if response.status_code in (301, 302):
            storage = get_messages(request)
            msgs = [str(m) for m in storage]
            return JsonResponse({
                'success': True,
                'message': msgs[0] if msgs else 'Saved successfully.',
                'redirect': response.get('Location', ''),
            })

        # Intercept POST responses that are NOT redirects but carry error messages
        # (e.g. delete view that re-renders because item is in use)
        if request.method == 'POST' and response.status_code == 200:
            storage = get_messages(request)
            msgs = []
            msg_tags = []
            for m in storage:
                msgs.append(str(m))
                msg_tags.append(m.tags)
            # Only convert to JSON if there are error/warning messages
            error_msgs = [m for m, t in zip(msgs, msg_tags) if 'error' in t or 'warning' in t]
            if error_msgs:
                return JsonResponse({
                    'success': False,
                    'message': error_msgs[0],
                })

        return response
