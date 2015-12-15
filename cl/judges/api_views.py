from cl.judges.filters import JudgeFilter
from cl.judges.serializers import JudgeSerializer
from cl.judges.models import Judge
from rest_framework import viewsets


class JudgesViewSet(viewsets.ModelViewSet):
    queryset = Judge.objects.all()
    serializer_class = JudgeSerializer
    filter_class = JudgeFilter
