"""
Общие константы приложения.
"""

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 МБ

ALLOWED_EXTENSIONS = {
    '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
    '.zip', '.rar', '.7z', '.png', '.jpg', '.jpeg', '.gif',
    '.txt', '.rtf', '.odt', '.ods', '.odp',
    # исходники кода
    '.py', '.java', '.c', '.cpp', '.h', '.hpp', '.cs', '.js', '.ts',
    '.jsx', '.tsx', '.html', '.css', '.sql', '.php', '.rb', '.go',
    '.rs', '.kt', '.swift', '.r', '.m', '.ipynb', '.json', '.xml',
    '.yaml', '.yml', '.md',
}

# Статусы работ для кабинетов студента и преподавателя
STATUS_LABELS = {
    "submitted": "Отправлено",
    "in_review": "На рассмотрении",
    "approved": "Зачтено",
    "rejected": "Не зачтено",
    "resubmitted": "Не зачтено (повторно отправлена)",
    "notebook_sent": "Тетрадь отправлена почтой",
}

# Статусы для раздела «Оценки» студента (формулировки отличаются)
STATUS_LABELS_GRADES = {
    "submitted":     "Отправлено",
    "in_review":     "На проверке",
    "approved":      "Зачтено",
    "rejected":      "Не зачтено",
    "resubmitted":   "Повторно отправлено",
    "notebook_sent": "Тетрадь отправлена",
}
