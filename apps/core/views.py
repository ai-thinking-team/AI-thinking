from django.shortcuts import render


def home(request):
    return render(request, 'core/home.html')


def subject_selection(request):
    return render(request, 'core/subject_selection.html')
