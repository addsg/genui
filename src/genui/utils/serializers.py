"""
serializers

Created by: Martin Sicho
On: 12/22/19, 6:26 PM
"""
from rest_framework import serializers


class GenericModelSerializerMixIn:
    className = serializers.CharField(required=False, allow_blank=True)
    extraArgs = serializers.DictField(required=False, allow_empty=True)

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        ret.update(self.getClassNameRepresentation(instance))
        ret.update(self.getExtraFieldsRepresentation(instance))
        return ret

    def getClassNameRepresentation(self, instance):
        ret = dict()
        model_class = instance.__class__
        if "className" in self.fields.keys():
            ret['className'] = model_class.__name__
        return ret

    def getExtraFieldsRepresentation(self, instance):
        ret = dict()
        if "extraArgs" in self.fields.keys():
            base_fields = set(self.Meta.model._meta.get_fields())
            derived_fields = set(instance.__class__._meta.get_fields())
            extra_fields = []
            for x in derived_fields - base_fields:
                if not x.name.endswith("_ptr"):
                    extra_fields.append(x.name)

            if extra_fields:
                serializer_class = self.getBaseSerializerClass(instance, extra_fields)
                extra_data = serializer_class(instance).data
                del extra_data['tasks'] # FIXME: this solves "GenericRelatedObjectManager is not JSON serializable" error with tasks, but I should look into it more (it should never fall under the extra_fields var above)
                ret['extraArgs'] = extra_data
            else:
                ret['extraArgs'] = {}
        return ret

    def getBaseSerializerClass(self, instance, extraFields):
        class GenericModelSerializer(serializers.ModelSerializer):

            class Meta:
                model = instance.__class__
                fields = extraFields
        return GenericModelSerializer