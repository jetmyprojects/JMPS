"""
URL configuration for todo_app project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.http import JsonResponse
from rest_framework import permissions
from drf_yasg.views import get_schema_view
from drf_yasg import openapi
from django.views.generic import TemplateView
from .views import index, contact_sales, sitemap

def health_check(request):
    return JsonResponse({"status": "healthy", "service": "Todo App API"})

schema_view = get_schema_view(
   openapi.Info(
      title="Todo App API",
      default_version='v1',
      description="API documentation for Todo App",
      terms_of_service="https://www.google.com/policies/terms/",
      contact=openapi.Contact(email="contact@todoapp.local"),
      license=openapi.License(name="BSD License"),
   ),
   public=True,
   permission_classes=(permissions.AllowAny,),
)

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', index, name='index'),
    path('api/v1/accounts/', include('accounts.urls')),
    path('api/v1/', include('tasks.urls')),
    path('api/v1/billing/', include('subscriptions.urls')),
    path('api/v1/storage/', include('storage.urls')),
    path('api/v1/payments/', include('payments.urls')),
    path('api/v1/admin/', include('adminpanel.urls')),
    path('', include('accounts.frontend_urls')),
    path('', include('tasks.frontend_urls')),
    path('', include('subscriptions.frontend_urls')),
    path('', include('adminpanel.frontend_urls')),
    path('health/', health_check, name='health_check'),
    path('docs/', schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui'),
    path('contact-sales/', contact_sales, name='contact_sales'),
    path('sitemap.xml', sitemap, name='sitemap'),
    path('how-it-works/', TemplateView.as_view(template_name='HowItWorks.html'), name='how_it_works'),
    path('terms/', TemplateView.as_view(template_name='TermsOfService.html'), name='terms'),
    path('privacy/', TemplateView.as_view(template_name='PrivacyPolicy.html'), name='privacy'),
    path('test-404/', TemplateView.as_view(template_name='404.html')),
    path('test-500/', TemplateView.as_view(template_name='500.html'))
]



from django.conf import settings
from django.conf.urls.static import static

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
else:
    # Force serve media files (and static if whitenoise fails) for Ngrok dev/staging
    from django.urls import re_path
    from django.views.static import serve
    import os
    
    # Serve static files directly from the source 'static' folder
    # This bypasses the need for collectstatic to succeed, which is failing silently presently
    urlpatterns += [
        re_path(r'^media/(?P<path>.*)$', serve, {'document_root': settings.MEDIA_ROOT}),
        re_path(r'^static/(?P<path>.*)$', serve, {'document_root': settings.BASE_DIR / 'static'}),
    ]
