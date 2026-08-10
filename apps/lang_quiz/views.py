from django.shortcuts import render


def home(request):
    return render(request, 'lang_quiz/home.html')
