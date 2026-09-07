from django.urls import path

from matches.views import (
    ChallengeAcceptView,
    ChallengeCancelView,
    ChallengeCreateView,
    ChallengeDetailView,
    ChallengeRejectView,
    MatchAnswersView,
    MatchBotView,
    MatchDetailView,
    MatchQuestionsView,
    MatchQuitView,
    MatchRematchView,
    MatchResultView,
    MatchStateView,
    MatchSubmitView,
)

urlpatterns = [
    path('challenges/', ChallengeCreateView.as_view(), name='challenge-create'),
    path('challenges/<int:id>/', ChallengeDetailView.as_view(), name='challenge-detail'),
    path('challenges/<int:id>/accept/', ChallengeAcceptView.as_view(), name='challenge-accept'),
    path('challenges/<int:id>/reject/', ChallengeRejectView.as_view(), name='challenge-reject'),
    path('challenges/<int:id>/cancel/', ChallengeCancelView.as_view(), name='challenge-cancel'),

    path('matches/bot/', MatchBotView.as_view(), name='match-bot'),
    path('matches/<int:id>/', MatchDetailView.as_view(), name='match-detail'),
    path('matches/<int:id>/questions/', MatchQuestionsView.as_view(), name='match-questions'),
    path('matches/<int:id>/state/', MatchStateView.as_view(), name='match-state'),
    path('matches/<int:id>/answers/', MatchAnswersView.as_view(), name='match-answers'),
    path('matches/<int:id>/submit/', MatchSubmitView.as_view(), name='match-submit'),
    path('matches/<int:id>/result/', MatchResultView.as_view(), name='match-result'),
    path('matches/<int:id>/quit/', MatchQuitView.as_view(), name='match-quit'),
    path('matches/<int:id>/rematch/', MatchRematchView.as_view(), name='match-rematch'),
]
