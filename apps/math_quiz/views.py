from django.shortcuts import render


def home(request):
    return render(request, 'math_quiz/home.html')
