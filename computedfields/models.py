from django.db import models
from .resolver import active_resolver, _ComputedFieldsModelBase
from django.contrib.contenttypes.models import ContentType
from django.utils.translation import ugettext_lazy as _


class ComputedFieldsModel(_ComputedFieldsModelBase, models.Model):
    """
    Abstract base class for models with computed fields. Overloads `save` to update
    local computed field values before they are written to the database.

    All models containing a computed field must be derived from this class.

    .. NOTE::

        If you have a custom save method in the inheritance chain that alters concrete field values,
        make sure that it is executed prior `ComputedFieldsModel.save`.
        Otherwise computed field values may not be in sync on database level.
        If in doubt, place `ComputedFieldsModel` higher up in the model inheritance.
    """
    class Meta:
        abstract = True
    
    def save(self, *args, **kwargs):
        """
        Overloaded to update computed field values before writing to the database.
        """
        new_update_fields = update_computedfields(self, kwargs.get('update_fields'))
        if new_update_fields:
            kwargs['update_fields'] = new_update_fields
        return super(ComputedFieldsModel, self).save(*args, **kwargs)


# some convenient access mappings

# decorators
#: Convenient access to the decorator :meth:`@computed<.resolver.Resolver.computed>`.
computed = active_resolver.computed
#: Convenient access to the decorator :meth:`@precomputed<.resolver.Resolver.precomputed>`.
precomputed = active_resolver.precomputed

# computed field updates
#: Convenient access to :meth:`compute<.resolver.Resolver.compute>`.
compute = active_resolver.compute
#: Convenient access to :meth:`update_computedfields<.resolver.Resolver.update_computedfields>`.
update_computedfields = active_resolver.update_computedfields
#: Convenient access to :meth:`update_dependent<.resolver.Resolver.update_dependent>`.
update_dependent = active_resolver.update_dependent
#: Convenient access to :meth:`update_dependent_multi<.resolver.Resolver.update_dependent_multi>`.
update_dependent_multi = active_resolver.update_dependent_multi
#: Convenient access to :meth:`preupdate_dependent<.resolver.Resolver.preupdate_dependent>`.
preupdate_dependent = active_resolver.preupdate_dependent
#: Convenient access to :meth:`preupdate_dependent_multi<.resolver.Resolver.preupdate_dependent_multi>`.
preupdate_dependent_multi = active_resolver.preupdate_dependent_multi

# helper
#: Convenient access to :meth:`has_computedfields<.resolver.Resolver.has_computedfields>`.
has_computedfields = active_resolver.has_computedfields
#: Convenient access to :meth:`is_computedfield<.resolver.Resolver.is_computedfield>`.
is_computedfield = active_resolver.is_computedfield
#: Convenient access to :meth:`get_contributing_fks<.resolver.Resolver.get_contributing_fks>`.
get_contributing_fks = active_resolver.get_contributing_fks


class ComputedModelManager(models.Manager):
    def get_queryset(self):
        objs = ContentType.objects.get_for_models(
            *active_resolver._computed_models.keys()).values()
        pks = [model.pk for model in objs]
        return ContentType.objects.filter(pk__in=pks)


class ComputedFieldsAdminModel(ContentType):
    """
    Proxy model to list all ``ComputedFieldsModel`` models with their
    field dependencies in admin. This might be useful during development.
    To enable it, set ``COMPUTEDFIELDS_ADMIN`` in settings.py to ``True``.
    """
    objects = ComputedModelManager()

    class Meta:
        proxy = True
        managed = False
        verbose_name = _('Computed Fields Model')
        verbose_name_plural = _('Computed Fields Models')
        ordering = ('app_label', 'model')


class ModelsWithContributingFkFieldsManager(models.Manager):
    def get_queryset(self):
        objs = ContentType.objects.get_for_models(
            *active_resolver._fk_map.keys()).values()
        pks = [model.pk for model in objs]
        return ContentType.objects.filter(pk__in=pks)


class ContributingModelsModel(ContentType):
    """
    Proxy model to list all models in admin, that contain fk fields contributing to computed fields.
    This might be useful during development.
    To enable it, set ``COMPUTEDFIELDS_ADMIN`` in settings.py to ``True``.
    An fk field is considered contributing, if it is part of a computed field dependency,
    thus a change to it would impact a computed field.
    """
    objects = ModelsWithContributingFkFieldsManager()

    class Meta:
        proxy = True
        managed = False
        verbose_name = _('Model with contributing Fk Fields')
        verbose_name_plural = _('Models with contributing Fk Fields')
        ordering = ('app_label', 'model')
