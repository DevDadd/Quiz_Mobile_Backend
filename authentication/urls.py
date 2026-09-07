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
                    ])

