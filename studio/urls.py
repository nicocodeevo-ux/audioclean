from django.urls import path
from . import views

app_name = 'studio'

urlpatterns = [
    path('', views.StudioView.as_view(), name='index'),
    path('upload/', views.UploadView.as_view(), name='upload'),
    path('analyze/<int:project_id>/', views.AnalyzeView.as_view(), name='analyze'),
    path('repair/<int:project_id>/', views.RepairView.as_view(), name='repair'),
    path('download-report/<int:project_id>/', views.DownloadReportView.as_view(), name='download_report'),
]
