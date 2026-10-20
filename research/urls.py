from django.urls import path

from . import views

urlpatterns = [
    path('', views.research, name='research'),
    path('create/', views.create_project, name='research_create'),
    path('update/', views.update_project, name='research_update'),
    path('delete/', views.delete_project, name='research_delete'),
    path('<int:pk>/', views.project_detail, name='research_project'),
    path('<int:pk>/paper/', views.paper, name='research_paper'),
    path('<int:pk>/paper/compile/', views.paper_compile, name='research_paper_compile'),
    path('<int:pk>/experiments/new/', views.experiment_form, name='research_experiment_create'),
    path(
        '<int:pk>/experiments/<int:experiment_id>/',
        views.experiment_detail,
        name='research_experiment',
    ),
    path(
        '<int:pk>/experiments/<int:experiment_id>/view/',
        views.experiment_view,
        name='research_experiment_view',
    ),
    path(
        '<int:pk>/experiments/<int:experiment_id>/files/<int:file_id>/',
        views.experiment_file,
        name='research_experiment_file',
    ),
    path(
        '<int:pk>/experiments/<int:experiment_id>/edit/',
        views.experiment_form,
        name='research_experiment_edit',
    ),
    path(
        '<int:pk>/experiments/<int:experiment_id>/delete/',
        views.experiment_delete,
        name='research_experiment_delete',
    ),
]
