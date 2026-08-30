from django.urls import path
from authentication.views import LoginView, MeView

urlpatterns = [
    path('login/', LoginView.as_view(), name='login'),
]
