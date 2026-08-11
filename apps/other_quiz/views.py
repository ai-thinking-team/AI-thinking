from django.shortcuts import render


def home(request):
    return render(request, 'other_quiz/home.html')
