"""Константы предметной области и подписи для интерфейса."""

MONTHLY_NORM_HOURS = 160
MIN_PASSWORD_LENGTH = 6
MAX_PASSWORD_LENGTH = 128
MAX_SHIFT_MINUTES = 16 * 60
MINUTES_PER_DAY = 24 * 60
MAX_SCHEDULE_DAYS = 366
MAX_NAME_LENGTH = 100
MAX_POSITION_LENGTH = 50
MAX_PHONE_LENGTH = 30
MIN_REASON_LENGTH = 3
MAX_REASON_LENGTH = 500
UPCOMING_SHIFTS_LIMIT = 5
DASHBOARD_REQUESTS_LIMIT = 5
EMPLOYEE_COLORS = 8

ROLES = {"manager": "Управляющий", "employee": "Сотрудник"}

SHIFT_STATUSES = {
    "planned": "Запланирована",
    "completed": "Отработана",
    "cancelled": "Отменена",
}

# Замена идёт в два шага: коллега соглашается, затем управляющий утверждает.
REQUEST_STATUSES = {
    "pending_colleague": "Ждёт ответа коллеги",
    "pending_manager": "Ждёт решения управляющего",
    "approved": "Одобрена",
    "rejected": "Отклонена управляющим",
    "declined": "Коллега отказался",
    "cancelled": "Отменена",
}
ACTIVE_REQUEST_STATUSES = ("pending_colleague", "pending_manager")
CLOSED_REQUEST_STATUSES = ("approved", "rejected", "declined", "cancelled")

POSITIONS = (
    "Бариста", "Официант", "Повар", "Кассир", "Продавец-консультант",
    "Администратор", "Кладовщик", "Хостес", "Бармен",
)

RU_MONTHS = (
    "", "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
    "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь",
)
RU_MONTHS_GENITIVE = (
    "", "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
)
RU_WEEKDAYS_SHORT = ("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс")
