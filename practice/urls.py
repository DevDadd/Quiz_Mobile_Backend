from django.urls import path

from practice.views import (
    PracticeQuestionsView,
    PracticeResultView,
    PracticeSessionCreateView,
    PracticeSessionDetailView,
    PracticeGradeView,
    PracticeSetQuestionsView,
    PracticeSetsView,
    PracticeSubmitView,
    WrongQuestionsView,
    WrongQuestionRecordView,
    QuestionOptionsView,
)

urlpatterns = [
    path('sets/', PracticeSetsView.as_view(), name='practice-sets'),
    path('sets/<int:id>/questions/', PracticeSetQuestionsView.as_view(), name='practice-set-questions'),
    path('questions/<int:question_id>/options/', QuestionOptionsView.as_view(), name='practice-question-options'),

    path('sessions/', PracticeSessionCreateView.as_view(), name='practice-session-create'),
    path('sessions/<int:id>/', PracticeSessionDetailView.as_view(), name='practice-session-detail'),
    path('sessions/<int:id>/questions/', PracticeQuestionsView.as_view(), name='practice-session-questions'),
    path('sessions/<int:id>/submit/', PracticeSubmitView.as_view(), name='practice-session-submit'),
    path('sessions/<int:id>/grade/', PracticeGradeView.as_view(), name='practice-session-grade'),
    path('sessions/<int:id>/record-wrong/', WrongQuestionRecordView.as_view(), name='practice-session-record-wrong'),
    path('sessions/<int:id>/result/', PracticeResultView.as_view(), name='practice-session-result'),

    path('wrong-questions/', WrongQuestionsView.as_view(), name='practice-wrong-questions'),
]
