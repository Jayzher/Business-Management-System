"""Forms for Superadmin user & role management."""
from django import forms
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

from accounts.models import User, Role, UserRole


_INPUT = {'class': 'form-control'}
_CHECK = {'class': 'form-check-input'}


class UserCreateForm(forms.ModelForm):
    """Create a new user with optional role assignment."""
    password1 = forms.CharField(
        label='Password',
        widget=forms.PasswordInput(attrs={**_INPUT, 'autocomplete': 'new-password'}),
        help_text='Minimum 8 characters.',
    )
    password2 = forms.CharField(
        label='Confirm Password',
        widget=forms.PasswordInput(attrs={**_INPUT, 'autocomplete': 'new-password'}),
    )
    roles = forms.ModelMultipleChoiceField(
        queryset=Role.objects.all().order_by('name'),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        help_text='Select one or more roles to assign. Superuser accounts bypass role checks.',
    )

    class Meta:
        model = User
        fields = [
            'username', 'first_name', 'last_name', 'email', 'phone',
            'is_active', 'is_staff', 'is_superuser',
        ]
        widgets = {
            'username': forms.TextInput(attrs=_INPUT),
            'first_name': forms.TextInput(attrs=_INPUT),
            'last_name': forms.TextInput(attrs=_INPUT),
            'email': forms.EmailInput(attrs=_INPUT),
            'phone': forms.TextInput(attrs=_INPUT),
            'is_active': forms.CheckboxInput(attrs=_CHECK),
            'is_staff': forms.CheckboxInput(attrs=_CHECK),
            'is_superuser': forms.CheckboxInput(attrs=_CHECK),
        }

    def __init__(self, *args, acting_user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.acting_user = acting_user
        # Only superusers can grant is_superuser or is_staff (Django admin) flags.
        if acting_user is not None and not acting_user.is_superuser:
            self.fields.pop('is_superuser', None)
            self.fields.pop('is_staff', None)

    def clean_password2(self):
        p1 = self.cleaned_data.get('password1')
        p2 = self.cleaned_data.get('password2')
        if p1 and p2 and p1 != p2:
            raise ValidationError('Passwords do not match.')
        if p1:
            validate_password(p1)
        return p2

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data['password1'])
        if commit:
            user.save()
            self._save_roles(user)
        return user

    def _save_roles(self, user):
        roles = self.cleaned_data.get('roles') or []
        existing = {ur.role_id: ur for ur in user.user_roles.all()}
        wanted_ids = {r.id for r in roles}
        # remove roles no longer wanted
        for role_id, ur in existing.items():
            if role_id not in wanted_ids:
                ur.delete()
        # add new
        for r in roles:
            if r.id not in existing:
                UserRole.objects.create(user=user, role=r)


class UserEditForm(forms.ModelForm):
    """Edit an existing user and their role assignments (no password)."""
    roles = forms.ModelMultipleChoiceField(
        queryset=Role.objects.all().order_by('name'),
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )

    class Meta:
        model = User
        fields = [
            'username', 'first_name', 'last_name', 'email', 'phone',
            'is_active', 'is_staff', 'is_superuser',
        ]
        widgets = {
            'username': forms.TextInput(attrs=_INPUT),
            'first_name': forms.TextInput(attrs=_INPUT),
            'last_name': forms.TextInput(attrs=_INPUT),
            'email': forms.EmailInput(attrs=_INPUT),
            'phone': forms.TextInput(attrs=_INPUT),
            'is_active': forms.CheckboxInput(attrs=_CHECK),
            'is_staff': forms.CheckboxInput(attrs=_CHECK),
            'is_superuser': forms.CheckboxInput(attrs=_CHECK),
        }

    def __init__(self, *args, acting_user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.acting_user = acting_user
        # Pre-select currently assigned roles
        if self.instance and self.instance.pk:
            self.fields['roles'].initial = Role.objects.filter(
                role_users__user=self.instance
            ).distinct()
        # Only superusers manage the superuser/is_staff flags
        if acting_user is not None and not acting_user.is_superuser:
            self.fields.pop('is_superuser', None)
            self.fields.pop('is_staff', None)

    def save(self, commit=True):
        user = super().save(commit=commit)
        if commit:
            self._save_roles(user)
        return user

    def _save_roles(self, user):
        roles = self.cleaned_data.get('roles') or []
        existing = {ur.role_id: ur for ur in user.user_roles.all()}
        wanted_ids = {r.id for r in roles}
        for role_id, ur in existing.items():
            if role_id not in wanted_ids:
                ur.delete()
        for r in roles:
            if r.id not in existing:
                UserRole.objects.create(user=user, role=r)


class PasswordResetForm(forms.Form):
    """Admin-initiated password reset for a target user."""
    password1 = forms.CharField(
        label='New Password',
        widget=forms.PasswordInput(attrs={**_INPUT, 'autocomplete': 'new-password'}),
        help_text='Minimum 8 characters.',
    )
    password2 = forms.CharField(
        label='Confirm New Password',
        widget=forms.PasswordInput(attrs={**_INPUT, 'autocomplete': 'new-password'}),
    )

    def clean_password2(self):
        p1 = self.cleaned_data.get('password1')
        p2 = self.cleaned_data.get('password2')
        if p1 and p2 and p1 != p2:
            raise ValidationError('Passwords do not match.')
        if p1:
            validate_password(p1)
        return p2


class RoleForm(forms.ModelForm):
    class Meta:
        model = Role
        fields = ['name', 'description']
        widgets = {
            'name': forms.TextInput(attrs=_INPUT),
            'description': forms.Textarea(attrs={**_INPUT, 'rows': 3}),
        }
