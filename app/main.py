from fastapi import FastAPI, Depends, HTTPException, WebSocket, Header, WebSocketDisconnect, Query, Request
from sqlalchemy.orm import Session
from . import database, auth, crud, models
from .schemas import *
from datetime import datetime
import logging
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


app = FastAPI()

database.create_tables_if_not_exists(database.engine)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = []
    for error in exc.errors():
        if error['loc'][-1] == 'password':
            errors.append("Пароль должен содержать не менее 5 символов.")
        if error['loc'][-1] == 'username':
            errors.append("Никнейм должен содержать не менее 4 символов.")
        if error['loc'][-1] == 'channel_name':
            errors.append("Название чата должно содержать хотя бы один символ.")

    return JSONResponse(
        status_code=422,
        content={"detail": errors}
    )


@app.post("/register") #регистрация
async def register(form: RegisterForm, db: Session = Depends(database.get_db)) -> dict:
    # Проверка, существует ли уже пользователь с таким именем
    existing_user = crud.get_user(db, form.username)
    if existing_user:
        raise HTTPException(status_code=400, detail="Пользователь с таким именем уже существует")
    # Хэширование пароля
    hashed_password = auth.hash_password(form.password)
    # Создание нового пользователя
    crud.create_user(db, user=form.username, hashed_password=hashed_password)
    return {"message": "Пользователь успешно зарегистрирован"}


@app.post("/login") #аутентификация, выдача токена
async def login(form: LoginForm, db: Session=Depends(database.get_db)) -> dict:
    user = auth.authenticate_user(db, form.username, form.password)
    logging.info("Авторизация")
    if not user:
        raise HTTPException(status_code=400, detail="Неправильный пароль/логин или пользователь не зарегистрирован.")
    access_token = auth.create_access_token(data={"user_id": user.id, "username": user.username})
    return {"access_token": access_token, "token_type": "bearer"}


# Создание нового канала
@app.post("/channels/create")
async def create_channel(form: ChannelCreate, token: str = Header(...), db: Session = Depends(database.get_db)):
    payload = auth.decode_access_token(token)
    if not payload:
        raise HTTPException(status_code=403, detail="Не авторизован.")
    user = db.query(models.User).filter_by(id=payload.get("user_id")).first()
    if user.is_blocked:
        raise HTTPException(status_code=400, detail="Пользователь заблокирован.")
    existing_channel = db.query(models.Channel).filter_by(name=form.channel_name).first()
    if existing_channel:
        raise HTTPException(status_code=400, detail="Канал с таким именем уже существует.")
    token_channel = crud.generate_invite_token()
    channel = models.Channel(name=form.channel_name, invite_token = token_channel, owner_id=user.id)
    db.add(channel)
    db.commit()
    db.refresh(channel)
    crud.add_user_to_channel(db, user_id=user.id, channel_id=channel.id)
    return {"message": "Канал успешно создан", "channel_name": channel.name, "channel_invite": channel.invite_token}


@app.post("/join/")
async def join_channel(invite_token: str = Header(...), user_token: str = Header(...), db: Session = Depends(database.get_db)):
    user = await auth.get_current_user(user_token, db)
    channel = crud.get_channel_by_invite_token(db, invite_token)
    if not channel:
        raise HTTPException(status_code=404, detail="Канал не найден или ссылка недействительна")
    
    if user.is_blocked:
        raise HTTPException(status_code=404, detail="Вы заблокированы")
    
    if crud.is_user_in_channel(db, user.id, channel.id):
        raise HTTPException(status_code=400, detail=f"Вы уже присоединились к этому каналу")
    crud.add_user_to_channel(db, user_id=user.id, channel_id=channel.id)
    return {"message": f"Вы успешно присоединились к каналу", "channel_name": channel.name, "username": user.username}


connected_users = {}
# WebSocket для отправки сообщений в канале
@app.websocket("/ws/chat/")
async def channel_chat(websocket: WebSocket, channel_name: str = Query(...), token: str = Header(...), db: Session = Depends(database.get_db)):
    logging.info("Попытка установить WebSocket соединение")
    await websocket.accept()
    logging.info("WebSocket соединение принято")
    try:
        payload = auth.decode_access_token(token)

        if not payload: # Недействительный токен
            logging.error("Недействительный токен")
            await websocket.close(code=403)
            return

        user_id = payload.get("user_id")
        username = payload.get("username")
        logging.info(f"User ID: {user_id}, Username: {username}")

        # Получаем пользователя из базы данных
        user = db.query(models.User).filter_by(id=user_id).first()
        if not user:
            logging.error("Пользователь не найден")
            await websocket.close(code=400)  # Пользователь не найден
            return

        # Проверяем наличие канала
        channel = db.query(models.Channel).filter_by(name=channel_name).first()
        if not channel:
            logging.error("Канал не найден")
            await websocket.send_text("Канал не найден")
            await websocket.close(code=404)  # Канал не найден
            return

        # Проверяем, является ли пользователь членом канала и не заблокирован ли он
        is_member = db.query(models.channel_users).filter_by(channel_id=channel.id, user_id=user.id).first()
        if not is_member or user.is_blocked:
            logging.error("Пользователь не является членом канала или заблокирован")
            await websocket.send_text("Вы не являетесь членом канала или заблокированы.")
            await websocket.close(code=403)
            return

        if channel.id not in connected_users:
            connected_users[channel.id] = []
        connected_users[channel.id].append(websocket)
        # Основной цикл получения и отправки сообщений
        while True:
            data = await websocket.receive_text()
            timestamp = datetime.now().isoformat()

            # Сохранение сообщения в базе данных
            message = models.Message(sender_id=user_id, content=data, timestamp=timestamp, channel_id=channel.id)
            db.add(message)
            db.commit()

            for conn in connected_users[channel.id]:
                await conn.send_text(f"[{timestamp}] {username}: {data}")
    except WebSocketDisconnect:
        logging.info(f"Пользователь {username} отключился от канала {channel_name}")
        connection_closed = True
    except Exception as e:
        logging.error(f"Ошибка: {e}")
        connection_closed = True
    finally:
        if websocket in connected_users.get(channel.id, []):
            connected_users[channel.id].remove(websocket)
        if not connection_closed:
            await websocket.close()


# Получение истории сообщений в канале
@app.get("/channels/messages")
async def get_channel_messages(channel_name: str = Query(...), token: str = Header(...), db: Session = Depends(database.get_db)):
    payload = auth.decode_access_token(token)
    if not payload:
        raise HTTPException(status_code=403, detail="Срок действия токена истек.")
    user_id = payload.get("user_id")
    user = db.query(models.User).filter_by(id=user_id).first()
    logging.info(f"User ID: {user_id}, Username: {user.username}")
    if not user_id:
        raise HTTPException(status_code=400, detail="Invalid token")
    channel = db.query(models.Channel).filter_by(name=channel_name).first()
    if not channel:
        raise HTTPException(status_code=404, detail="Канал не найден")
    # Проверка членства пользователя в канале
    is_member = db.query(models.channel_users).filter_by(channel_id=channel.id, user_id=user_id).first()
    if not (is_member or user.role == "moderator") or user.is_blocked:
        raise HTTPException(status_code=403, detail="Доступ запрещен")
    messages = db.query(models.Message, models.User.username).join(models.User, models.Message.sender_id == models.User.id).filter(
        models.Message.channel_id == channel.id).order_by(models.Message.timestamp.asc()).all()
    if not messages:
        return {"Чат пуст"}
    return {"messages": [
            {"username": username, "content": msg.content, "timestamp": msg.timestamp.isoformat()}
            for msg, username, in messages
            ]}


@app.post("/users/block")
async def block_user(user_name: str = Query(...), token: str = Header(...), db: Session = Depends(database.get_db)):
    payload = auth.decode_access_token(token)
    if not payload:
        raise HTTPException(status_code=403, detail="Срок действия токена истек.")
    current_user = db.query(models.User).filter_by(id=payload.get("user_id")).first()
    # Проверяем, что текущий пользователь — модератор
    if current_user.role != "moderator":
        raise HTTPException(status_code=403, detail="Недостаточно прав для блокировки пользователя")
    # Находим пользователя для блокировки
    user_to_block = db.query(models.User).filter(models.User.username == user_name).first()
    if not user_to_block:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    # Проверяем, не является ли уже пользователь заблокированным
    if user_to_block.is_blocked:
        raise HTTPException(status_code=400, detail="Пользователь уже заблокирован")
    # Блокируем пользователя
    user_to_block.is_blocked = True
    db.commit()
    return {"message": f"Пользователь {user_to_block.username} успешно заблокирован"}