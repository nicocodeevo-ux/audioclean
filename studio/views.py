import os
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.views import View
from .models import AudioProject
import json

class StudioView(View):
    def get(self, request):
        projects = AudioProject.objects.all().order_by('-created_at')
        return render(request, 'studio/index.html', {'projects': projects})

class UploadView(View):
    def post(self, request):
        if 'audio_file' in request.FILES:
            audio_file = request.FILES['audio_file']
            project = AudioProject.objects.create(original_file=audio_file)
            return JsonResponse({'status': 'success', 'project_id': project.id, 'url': project.original_file.url})
        return JsonResponse({'status': 'error', 'message': 'No file uploaded'}, status=400)

from .audio_processor import repair_audio, analyze_audio, generate_suggestions, generate_engineer_report

from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt

@method_decorator(csrf_exempt, name='dispatch')
class AnalyzeView(View):
    def post(self, request, project_id):
        project = get_object_or_404(AudioProject, id=project_id)
        
        # Determine which file to analyze (processed if exists, else original)
        file_path = project.processed_file.path if project.processed_file else project.original_file.path
        
        analysis_result, error_message = analyze_audio(file_path)
        
        if analysis_result is not None and error_message is None:
            # Generate suggestions
            suggestions = generate_suggestions(analysis_result)
            
            project.analysis_data = analysis_result
            project.save()
            
            # Flatten response for frontend
            response_data = {'status': 'success'}
            response_data.update(analysis_result)
            response_data['suggestions'] = suggestions
            return JsonResponse(response_data)
        else:
            return JsonResponse({'status': 'error', 'message': error_message}, status=500)

class RepairView(View):
    def post(self, request, project_id):
        project = get_object_or_404(AudioProject, id=project_id)
        data = json.loads(request.body)
        action = data.get('action')
        params = data.get('params', {})
        
        # Always process from the original to avoid generational loss? 
        # Or process the last version? Let's process the current state.
        source_file_path = project.processed_file.path if project.processed_file else project.original_file.path
        
        processed_rel_path = repair_audio(source_file_path, action, params, project=project)
        
        if processed_rel_path == "METADATA_UPDATE_ONLY":
            return JsonResponse({
                'status': 'success', 
                'message': 'Noise profile learned',
            })
        
        if processed_rel_path:
            # Update the project with the new file
            project.processed_file.name = processed_rel_path
            project.save()
            
            return JsonResponse({
                'status': 'success', 
                'message': f'Applied {action}',
                'url': project.processed_file.url
            })
        else:
            return JsonResponse({'status': 'error', 'message': 'Repair failed'}, status=500)

from django.http import HttpResponse

class DownloadReportView(View):
    def get(self, request, project_id):
        project = get_object_or_404(AudioProject, id=project_id)
        
        if not project.analysis_data:
            return HttpResponse("No analysis data available. Please run analysis first.", status=400)
        
        # Get filename
        filename = os.path.basename(project.original_file.name)
        
        # Generate report
        report_text = generate_engineer_report(project.analysis_data, filename)
        
        # Create HTTP response with text file
        response = HttpResponse(report_text, content_type='text/plain')
        response['Content-Disposition'] = f'attachment; filename="report_{project.id}_{filename}.txt"'
        
        return response
