from django.urls import path

from practice.views import (
    PracticeAnswersView,
    PracticeQuestionsView,
    PracticeResultView,
    PracticeSessionCreateView,
    PracticeSessionDetailView,
    PracticeSetQuestionsView,
    PracticeSetsView,
    PracticeSubmitView,
    WrongQuestionsView,
)

urlpatterns = [
    path('sets/', PracticeSetsView.as_view(), name='practice-sets'),
    path('sets/<int:id>/questions/', PracticeSetQuestionsView.as_view(), name='practice-set-questions'),

    path('sessions/', PracticeSessionCreateView.as_view(), name='practice-session-create'),
    path('sessions/<int:id>/', PracticeSessionDetailView.as_view(), name='practice-session-detail'),
    path('sessions/<int:id>/questions/', PracticeQuestionsView.as_view(), name='practice-session-questions'),
    path('sessions/<int:id>/answers/', PracticeAnswersView.as_view(), name='practice-session-answers'),
    path('sessions/<int:id>/submit/', PracticeSubmitView.as_view(), name='practice-session-submit'),
    path('sessions/<int:id>/result/', PracticeResultView.as_view(), name='practice-session-result'),

    path('wrong-questions/', WrongQuestionsView.as_view(), name='practice-wrong-questions'),
]
