from django.test import TestCase
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.exceptions import ValidationError
from tasks.models import Task, TaskFile
from accounts.models import User
from rest_framework.test import APIClient
from rest_framework import status

class FileUploadRestrictionTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='password')
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.task = Task.objects.create(user=self.user, project_name="Test Project")

    def test_upload_allowed_extension(self):
        # Create a dummy PDF file
        pdf_content = b"%PDF-1.4..."
        pdf_file = SimpleUploadedFile("test.pdf", pdf_content, content_type="application/pdf")
        
        # Test Model Validation directly
        task_file = TaskFile(task=self.task, file=pdf_file)
        try:
            task_file.full_clean() # Should not raise error
            task_file.save()
        except ValidationError:
            self.fail("Allowed file type (PDF) raised ValidationError")

    def test_upload_disallowed_extension(self):
        # Create a dummy TXT file
        txt_content = b"This is a text file"
        txt_file = SimpleUploadedFile("test.txt", txt_content, content_type="text/plain")
        
        task_file = TaskFile(task=self.task, file=txt_file)
        with self.assertRaises(ValidationError):
            task_file.full_clean()

    def test_api_upload_disallowed_extension(self):
        # Test via API to check Serializer validation
        txt_content = b"This is a text file"
        txt_file = SimpleUploadedFile("test.txt", txt_content, content_type="text/plain")
        
        payload = {
            'project_name': 'API Test Project',
            'uploaded_files': [txt_file]
        }
        
        response = self.client.post('/api/v1/tasks/', payload, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Unsupported file type", str(response.data))

    def test_api_upload_allowed_extension(self):
        # Test via API to check Serializer validation
        png_content = b"\x89PNG\r\n\x1a\n"
        png_file = SimpleUploadedFile("test.png", png_content, content_type="image/png")
        
        payload = {
            'project_name': 'API Test Project 2',
            'uploaded_files': [png_file]
        }
        
        response = self.client.post('/api/v1/tasks/', payload, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
