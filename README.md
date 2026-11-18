# LOG SENTINEL // REAL-TIME TELEMETRY STREAM & SPIKE ANALYZER

![Version](https://img.shields.io/badge/version-1.0.0-lime)
![Backend](https://img.shields.io/badge/backend-FastAPI%20%2B%20WebSockets-009688)
![Telemetry](https://img.shields.io/badge/stream-Loki%20Pulse%20Stream-84CC16)
![Database](https://img.shields.io/badge/storage-SQLite%20Log%20Vault-0284C7)

Высокопроизводительная система сбора, стриминга и интеллектуального анализа логов в реальном времени (легковесный self-hosted аналог Grafana Loki и Datadog): стриминг событий через WebSocket, фильтрация по уровням (ERROR, WARN, INFO, DEBUG), полнотекстовый поиск по подстрокам и регулярным выражениям, графики всплесков аномалий по минутам на HTML5 Canvas и модуль срабатывания алертов при превышении пороговых значений.

## Ключевой инженерный функционал

- **WebSocket Stream Pipeline:** Нулевая задержка доставки логов в браузер с авто-восстановлением соединения.
- **Встроенный генератор производственных логов:** Автономный фоновый демон имитирует реальный трафик (Nginx HTTP access, аутентификацию, пулы подключений PostgreSQL, асинхронные воркеры Celery).
- **Canvas-гистограмма всплесков аномалий:** Минутные бакеты с разбивкой по критичности (ошибки, предупреждения, информационные сообщения).
- **Сторожевой алерт-таймер (Alert Engine):** Настраиваемые правила (например: «более 3 ошибок за 30 секунд»), всплывающий аварийный баннер и процедурный акустический сигнал WebAudio API при нарушении SLA.
- **SQLite Log Vault:** Персистентное хранение логов, индексы по уровням и временным меткам, история срабатывания алертов.

## Запуск в 1 клик

```cmd
start.bat
```
Скрипт установит `fastapi`, `websockets`, `uvicorn` и откроет консоль Log Sentinel на `http://localhost:8017`.
