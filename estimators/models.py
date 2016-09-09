import datetime
import os
import dill

from sklearn.externals import joblib

from django.core.files.base import ContentFile
from django.core.exceptions import ValidationError

from django.db import models
from django.apps import apps
from django.conf import settings


class Estimator(models.Model):

    """
    A class that loads and persists different models
    """

    create_date = models.DateTimeField(auto_now_add=True, blank=False, null=False)
    description = models.CharField(max_length=256)
    estimator_hash = models.CharField(max_length=64, unique=True, default=None, null=False, editable=False)
    estimator_file = models.FileField(upload_to=settings.ESTIMATOR_UPLOAD_DIR, default=None, null=False, blank=True, editable=False)
    _estimator = None

    class Meta:
        db_table = 'estimators'

    def __repr__(self):
        return '<Estimator <Id %s> <Hash %s>: %s>' % (self.id, self.estimator_hash, self.estimator)

    @property
    def is_estimator_persisted(self):
        return self.estimator_file.name is not None and os.path.isfile(self.estimator_file.path)

    @classmethod
    def _compute_hash(cls, obj):
        return joblib.hash(obj)

    @classmethod
    def get_by_estimator(cls, est):
        if est is not None:
            estimator_hash = cls._compute_hash(est)
        return cls.get_by_estimator_hash(estimator_hash)

    @classmethod
    def get_by_estimator_hash(cls, estimator_hash):
        query_set = cls.objects.filter(estimator_hash=estimator_hash)
        return query_set.first()

    @classmethod
    def get_or_create(cls, estimator):
        estimator_hash = cls._compute_hash(estimator)
        obj = cls.get_by_estimator_hash(estimator_hash)
        if not obj:
            # create object
            obj = cls()
            obj.estimator = estimator
        return obj

    @property
    def estimator(self):
        # return cached model into cache if the model is available in a file
        if self._estimator is None:
            self._load_estimator()
        return self._estimator

    @estimator.setter
    def estimator(self, est):
        estimator_hash = self._compute_hash(est)
        self._estimator = est
        self.estimator_hash = estimator_hash
        self.estimator_file.name = self.estimator_hash

    def save(self, *args, **kwargs):
        self.full_clean(exclude=['description'])
        if not self.is_estimator_persisted:
            self._persist_estimator()
        super(Estimator, self).save(*args, **kwargs)

    def clean(self):
        if self.estimator_hash != self._compute_hash(self.estimator):
            raise ValidationError("estimator_hash '%s' should be set by the estimator '%s'" % (self.estimator_hash, self.estimator))
        # if already persisted, do not update estimator
        obj = self.get_by_estimator_hash(self.estimator_hash)
        if self.id and self.estimator_hash != getattr(obj, 'estimator_hash', None):
            raise ValidationError("Cannot persist updated estimator '%s'.  Create a new Estimator object." % self.estimator)

    def _persist_estimator(self):
        if self.estimator_hash:
            data = dill.dumps(self.estimator)
            f = ContentFile(data)
            self.estimator_file.save(self.estimator_hash, f)
            f.close()
            return True
        return False

    def _load_estimator(self):
        # to force loading a estimator
        if self.is_estimator_persisted:
            self.estimator_file.open()
            self.estimator = dill.loads(self.estimator_file.read())
            self.estimator_file.close()

    @classmethod
    def create_from_file(cls, filename):
        obj = cls()
        obj.estimator_file = filename
        obj._load_estimator()
        return obj
