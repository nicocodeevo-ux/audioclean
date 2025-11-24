from django.db import models
import os

class AudioProject(models.Model):
    name = models.CharField(max_length=255)
    original_file = models.FileField(upload_to='audio/originals/')
    processed_file = models.FileField(upload_to='audio/processed/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Analysis data stored as JSON
    analysis_data = models.JSONField(default=dict, blank=True)
    
    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.name and self.original_file:
            self.name = os.path.basename(self.original_file.name)
        super().save(*args, **kwargs)
