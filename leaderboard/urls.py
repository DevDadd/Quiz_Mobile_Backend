from django.urls import path
from .views import OnlinePlayersView, LeaderboardView, UserStatsView, UserMatchesView

urlpatterns = [
    path('online-players/', OnlinePlayersView.as_view(), name='online-players'),
    path('leaderboard/', LeaderboardView.as_view(), name='leaderboard'),
    path('users/<int:id>/stats/', UserStatsView.as_view(), name='user-stats'),
    path('users/<int:id>/matches/', UserMatchesView.as_view(), name='user-matches'),
]
