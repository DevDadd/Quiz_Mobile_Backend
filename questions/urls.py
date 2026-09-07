from django.urls import path
from .views import QuestionsView, QuestionDetailView

urlpatterns = [
    path('questions/', QuestionsView.as_view(), name='questions'),
    path('questions/<int:id>/', QuestionDetailView.as_view(), name='question-detail'),
]
