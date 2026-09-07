from django.urls import path
from authentication.views import LoginView, RegisterView, LogoutView, HeartbeatView, MeView

urlpatterns = [
    path('login/', LoginView.as_view(), name='login'),
    path('register/', RegisterView.as_view(), name='register'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('me/', MeView.as_view(), name='me'),
    path('session/heartbeat/', HeartbeatView.as_view(), name='heartbeat'),
]
