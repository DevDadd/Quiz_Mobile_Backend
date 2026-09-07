from django.urls import path
from authentication.views import LoginView

urlpatterns = [
    path('login/', LoginView.as_view(), name='login'),
]
from authentication.views import RegisterView, LogoutView, HeartbeatView, MeView, OnlinePlayersView

urlpatterns.extend([
    path('register/', RegisterView.as_view(), name='register'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('me/', MeView.as_view(), name='me'),
    path('session/heartbeat/', HeartbeatView.as_view(), name='heartbeat'),
    path('players/online/', OnlinePlayersView.as_view(), name='players_online'),
])

from authentication.views import LeaderboardView, UserStatsView, UserMatchesView, QuestionsView, QuestionDetailView

urlpatterns.extend([
    path('leaderboard/', LeaderboardView.as_view(), name='leaderboard'),
    path('users/<int:id>/stats/', UserStatsView.as_view(), name='user_stats'),
    path('users/<int:id>/matches/', UserMatchesView.as_view(), name='user_matches'),
    path('questions/', QuestionsView.as_view(), name='questions'),
    path('questions/<int:id>/', QuestionDetailView.as_view(), name='question_detail'),
])
