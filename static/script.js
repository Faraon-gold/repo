// Общие скрипты для системы учёта посещаемости

// Функция для получения cookie
function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}

// Добавляем CSRF защиту к каждому запросу
document.addEventListener('DOMContentLoaded', function() {
    // Здесь можно добавить общие скрипты для всей системы
    console.log('Система учёта посещаемости загружена');
});

// Функция для показа анимации при добавлении пользователя
function showUserAddedAnimation() {
    // Создаем контейнер для анимации
    const animationContainer = document.createElement('div');
    animationContainer.id = 'user-added-animation';
    animationContainer.style.position = 'fixed';
    animationContainer.style.top = '20px';
    animationContainer.style.right = '20px';
    animationContainer.style.zIndex = '9999';
    animationContainer.style.backgroundColor = '#28a745';
    animationContainer.style.color = 'white';
    animationContainer.style.padding = '15px 20px';
    animationContainer.style.borderRadius = '5px';
    animationContainer.style.boxShadow = '0 4px 12px rgba(0,0,0,0.15)';
    animationContainer.style.opacity = '0';
    animationContainer.style.transform = 'translateX(100px)';
    animationContainer.style.transition = 'all 0.3s ease-in-out';
    animationContainer.innerHTML = '<strong>Пользователь добавлен</strong>';
    
    document.body.appendChild(animationContainer);
    
    // Анимация появления
    setTimeout(() => {
        animationContainer.style.opacity = '1';
        animationContainer.style.transform = 'translateX(0)';
    }, 10);
    
    // Удаляем анимацию через 3 секунды
    setTimeout(() => {
        animationContainer.style.opacity = '0';
        animationContainer.style.transform = 'translateX(100px)';
        
        setTimeout(() => {
            if (document.body.contains(animationContainer)) {
                document.body.removeChild(animationContainer);
            }
        }, 300);
    }, 3000);
}

// Экспортируем функцию глобально, чтобы можно было вызвать из других мест
window.showUserAddedAnimation = showUserAddedAnimation;