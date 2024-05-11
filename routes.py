import os

import motor.motor_asyncio
from fastapi import FastAPI, HTTPException, Body, status, Depends
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
from pymongo import ReturnDocument#, ObjectId
from dotenv import load_dotenv
from bson import ObjectId

import models
import schemas

import bcrypt
import auth
from auth import JWTBearer


load_dotenv()


app = FastAPI(
    title="Coordimate Backend API",
    summary="Backend of the Coordimate mobile application that fascilitates group meetings",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
client = motor.motor_asyncio.AsyncIOMotorClient(os.environ["MONGODB_URL"])
db = client.coordimate
user_collection = db.get_collection("users")
meetings_collection = db.get_collection("meetings")
group_collection = db.get_collection("groups")


# ********** Authentification **********

@app.post(
    "/login",
    response_description="Authentificate a user",
    response_model=schemas.TokenSchema,
    status_code=status.HTTP_200_OK,
    response_model_by_alias=False,
)
async def login(user: schemas.LoginUserSchema = Body(...)):
    if (user_found := await user_collection.find_one({"email":user.email})) is not None:
        user_found["id"] = user_found.pop("_id")
        if bcrypt.checkpw(user.password.encode("utf-8"), user_found["password"]):
            token = auth.generateToken(user_found)
            return token
        else:
            raise HTTPException(status_code=400, detail=f"password incorrect")

    raise HTTPException(status_code=404, detail=f"user {user.email} not found")

@app.post(
    "/refresh",
    response_description="Refresh a token",
    response_model=schemas.TokenSchema,
    status_code=status.HTTP_200_OK,
    response_model_by_alias=False,
)
async def refresh_token(token: schemas.RefreshTokenSchema = Body(...)):
    decoded_token = auth.decodeJWT(token.refresh_token)
    if (decoded_token is None) or (decoded_token.is_access_token != False):
        raise HTTPException(status_code=401, detail="Invalid token or expired token.")
    new_token = auth.generate_refresh_token(token.refresh_token, decoded_token)
    return new_token

@app.get(
    "/me",
    response_description="Get account information",
    response_model=schemas.AccountOut
)
async def me(user: schemas.AuthSchema = Depends(JWTBearer())):
    user_found = await user_collection.find_one({"_id": ObjectId(user.id)})
    if user_found is None:
        raise HTTPException(status_code=404, detail="Account not found")
    return schemas.AccountOut(id=str(user_found["_id"]), email=user_found["email"])

# ********** Users **********

@app.post(
    "/register",
    response_description="Add new user",
    response_model=models.UserModel,
    status_code=status.HTTP_201_CREATED,
    response_model_by_alias=False,
)
async def register(user: schemas.CreateUserSchema = Body(...)):
    existing_user = await user_collection.find_one({"email": user.email})
    if existing_user:
        raise HTTPException(status_code=400, detail="User already exists")
    user.password = bcrypt.hashpw(user.password.encode("utf-8"), bcrypt.gensalt())
    new_user = await user_collection.insert_one(
        user.model_dump(by_alias=True, exclude={"id"})
    )
    created_user = await user_collection.find_one({"_id": new_user.inserted_id})
    return created_user

@app.get(
    "/users/",
    response_description="List all users",
    response_model=models.UserCollection,
    response_model_by_alias=False,
)
async def list_users():
    return models.UserCollection(users=await user_collection.find().to_list(1000))

@app.get(
    "/users/{id}",
    response_description="Get a single user",
    response_model=models.UserModel,
    response_model_by_alias=False,
)
async def show_user(id: str):
    if (user := await user_collection.find_one({"_id": ObjectId(id)})) is not None:
        return user

    raise HTTPException(status_code=404, detail=f"user {id} not found")

@app.put(
    "/users/{id}",
    response_description="Update a user",
    response_model=models.UserModel,
    response_model_by_alias=False,
)
async def update_user(id: str, user: models.UpdateUserModel = Body(...)):
    user_dict = {
        k: v for k, v in user.model_dump(by_alias=True).items() if v is not None
    }

    if len(user_dict) >= 1:
        update_result = await user_collection.find_one_and_update(
            {"_id": ObjectId(id)},
            {"$set": user_dict},
            return_document=ReturnDocument.AFTER,
        )
        if update_result is not None:
            return update_result
        else:
            raise HTTPException(status_code=404, detail=f"user {id} not found")

    if (existing_user := await user_collection.find_one({"_id": id})) is not None:
        return existing_user

    raise HTTPException(status_code=404, detail=f"user {id} not found")


@app.delete(
    "/users/{id}", 
    response_description="Delete a user"
)
async def delete_user(id: str):
    delete_result = await user_collection.delete_one({"_id": ObjectId(id)})

    if delete_result.deleted_count == 1:
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    raise HTTPException(status_code=404, detail=f"user {id} not found")

# ********** Time Slots **********

@app.get(
    "/time_slots/",
    response_description="List all time slots",
    response_model=schemas.TimeSlotCollection,
    response_model_by_alias=False,
)
async def list_time_slots(user: schemas.AuthSchema = Depends(JWTBearer())):
    user_found = await get_user(user.id)
    schedule = user_found.get("schedule")
    if schedule is None:
        return schemas.TimeSlotCollection(time_slots=[])
    return schemas.TimeSlotCollection(time_slots=schedule)


@app.post(
    "/time_slots/",
    response_description="Add new time slot",
    response_model=models.TimeSlot,
    status_code=status.HTTP_201_CREATED,
    response_model_by_alias=False,
)
async def create_time_slot(
        time_slot: schemas.CreateTimeSlot = Body(...),
        user: schemas.AuthSchema = Depends(JWTBearer())
    ):
    user_found = await get_user(user.id)
    if not user_found.get("schedule"):
        user_found["schedule"] = []
        new_id = -1
    else:
        new_id = user_found["schedule"][-1]["_id"]

    new_time_slot = time_slot.model_dump(by_alias=True)
    new_time_slot["_id"] = new_id + 1
    user_found["schedule"].append(new_time_slot)

    await user_collection.update_one(
        {"_id": user_found["_id"]},
        {"$set": {"schedule": user_found["schedule"]}}
    )
    return new_time_slot


@app.patch(
    "/time_slots/{slot_id}",
    response_description="Update a time slot",
    response_model=models.TimeSlot,
    response_model_by_alias=False,
)
async def update_time_slot(
        slot_id: int,
        time_slot: schemas.UpdateTimeSlot = Body(...),
        user: schemas.AuthSchema = Depends(JWTBearer())
    ):
    user_found = await get_user(user.id)
    time_slot_dict = {
        k: v for k, v in time_slot.model_dump(by_alias=True).items() if v is not None
    }
    schedule = user_found['schedule']
    for i in range(len(schedule)):
        if schedule[i]["_id"] == slot_id:
            schedule[i].update(time_slot_dict)
            break

    update_result = await user_collection.update_one(
        {'_id': ObjectId(user_found['_id'])},
        {'$set': {'schedule': schedule}}
    )
    if update_result.modified_count != 1:
        raise HTTPException(status_code=404, detail=f"time_slot {slot_id} not found")

    user_found = await get_user(user.id)
    for i in range(len(schedule)):
        if schedule[i]["_id"] == slot_id:
            return schedule[i]


@app.delete(
    "/time_slots/{slot_id}", 
    response_description="Delete a time slot"
)
async def delete_time_slot(slot_id: int, user: schemas.AuthSchema = Depends(JWTBearer())):
    user_found = await get_user(user.id)

    delete_result = await user_collection.update_one(
        {'_id': ObjectId(user_found['_id'])},
        {'$pull': {'schedule': {'_id': slot_id}}}
    )
    if delete_result.modified_count == 1:
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    raise HTTPException(status_code=404, detail=f'time_slot {id} not found')

# ********** Meetings **********

@app.post(
    "/meetings/",
    response_description="Add new meeting",
    response_model=models.MeetingModel,
    status_code=status.HTTP_201_CREATED,
    response_model_by_alias=False,
)
async def create_meeting(meeting: schemas.CreateMeeting = Body(...), user: schemas.AuthSchema = Depends(JWTBearer())):
    user_found = await get_user(user.id)
    meeting.admin_id = str(user_found["_id"])
    new_meeting = await meetings_collection.insert_one(
        meeting.model_dump(by_alias=True, exclude={"id"})
    )
    created_meeting = await meetings_collection.find_one({"_id": new_meeting.inserted_id})
    if created_meeting is None:
        raise HTTPException(status_code=500, detail="Error creating a meeting")
    # If the user has no meetings yet, create an empty list
    if user_found.get("meetings") is None:
        user_found["meetings"] = []
    # Add the meeting to the user's meetings list
    user_found["meetings"].append({"meeting_id": str(created_meeting["_id"]), "status": models.MeetingStatus.needs_acceptance.value})
    # Update the user document with the new meetings list
    await user_collection.update_one(
        {"_id": user_found["_id"]},
        {"$set": {"meetings": user_found["meetings"]}}
    )
    # Add yourself as a participant
    created_meeting["participants"] = [{"user_id": str(user_found["_id"]), "status": models.MeetingStatus.needs_acceptance.value}]
    await meetings_collection.update_one(
        {"_id": created_meeting["_id"]},
        {"$set": {"participants": created_meeting["participants"]}}
    )
    return created_meeting

@app.get(
    "/meetings/all",
    response_description="List all meetings",
    response_model=schemas.MeetingCollection,
    response_model_by_alias=False,
)
async def list_meetings():
    return schemas.MeetingCollection(meetings=await meetings_collection.find().to_list(1000))

@app.get(
    "/meetings/",
    response_description="List all meetings of a user",
    response_model=schemas.MeetingTileCollection,
    response_model_by_alias=False,
)
async def list_user_meetings(user: schemas.AuthSchema = Depends(JWTBearer())):
    user_found = await get_user(user.id)
    meeting_invites = user_found.get("meetings", [])
    meetings = []
    for invite in meeting_invites:
        meeting = await meetings_collection.find_one({"_id": ObjectId(invite["meeting_id"])})
        if meeting is not None:
            meeting_tile = schemas.MeetingTile(
                id=str(meeting["_id"]),
                title=meeting["title"],
                start=meeting["start"],
                group_id=str(meeting["group_id"]),  # Assuming group_id is stored as ObjectId
                status=invite["status"]
            )
            meetings.append(meeting_tile)
        
    return schemas.MeetingTileCollection(meetings=meetings)

@app.get(
    "/meetings/{id}",
    response_description="Get a single meeting",
    response_model=models.MeetingModel,
    response_model_by_alias=False,
)
async def show_meeting(id: str):
    if (meeting := await meetings_collection.find_one({"_id": ObjectId(id)})) is not None:
        return meeting
    
    raise HTTPException(status_code=404, detail=f"meeting {id} not found")

@app.get(
    "/meetings/{id}/details",
    response_description="Get details of a single meeting",
    response_model=schemas.MeetingDetails,
    response_model_by_alias=False,
)
async def show_meeting_details(id: str, user: schemas.AuthSchema = Depends(JWTBearer())):
    user_found = await get_user(user.id)
    meeting = await get_meeting(id)
    # meeting = MeetingModel
    meeting_participants = meeting.get("participants", [])
    participants = []
        # meeting_participants = List[Participant]
    for meeting_participant in meeting_participants:
            # meeting_participant = Participant
        participant_user = await get_user(str(meeting_participant["user_id"]))
            # participant_user = UserModel
        if participant_user is not None:
            participant = schemas.ParticipantSchema(
                user_id=str(participant_user["_id"]),
                user_username=participant_user["username"],
                status=meeting_participant["status"]
            )
            participants.append(participant)
                
    meeting_invites = user_found.get("meetings", [])
    for invite in meeting_invites:
        if (invite["meeting_id"] == id):
            meeting_tile = schemas.MeetingDetails(
                id=str(meeting["_id"]),
                title=meeting["title"],
                start=meeting["start"],
                group_id=str(meeting["group_id"]),
                admin_id=str(meeting["admin_id"]),
                description=meeting["description"],
                participants=participants,
                status=invite["status"]
            )
            return meeting_tile
    
@app.patch(
    "/meetings/{id}/change_participant_status",
    response_description="Change status of participant in a meeting",
    response_model=schemas.ParticipantInviteSchema,
    response_model_by_alias=False,
)
async def change_participant_status(id: str, participant: schemas.UpdateParticipantStatus = Body(...), user: schemas.AuthSchema = Depends(JWTBearer())):
    # user here is the admin
    await get_user(participant.id)
    await get_meeting(id)
    check_status(participant.status)
    await meeting_in_user(participant.id, id, participant.status)
    await participant_in_meeting(participant.id, id, participant.status)
    return schemas.ParticipantInviteSchema(meeting_id=id, user_id=participant.id, status=participant.status)   

@app.post(
    "/meetings/{id}/invite",
    response_description="Invite user to a meeting",
    response_model=schemas.ParticipantInviteSchema,
    response_model_by_alias=False,
)
async def invite(id: str, user: schemas.AuthSchema = Depends(JWTBearer())):
    await get_user(user.id)
    await get_meeting(id)
    await participant_in_meeting(user.id, id, models.MeetingStatus.needs_acceptance.value)
    await meeting_in_user(user.id, id, models.MeetingStatus.needs_acceptance.value)
    return schemas.ParticipantInviteSchema(meeting_id=id, user_id=user.id, status=models.MeetingStatus.needs_acceptance.value)

@app.patch(
    "/invites/{id}",
    response_description="Change status of invitation",
    response_model=models.MeetingInvite,
    response_model_by_alias=False,
)
async def change_invite_status(id: str, status: schemas.UpdateMeetingStatus = Body(...), user: schemas.AuthSchema = Depends(JWTBearer())):
    check_status(status.status)
    await get_user(user.id)
    await get_meeting(id)
    await meeting_in_user(user.id, id, status.status)
    await participant_in_meeting(user.id, id, status.status)
    return models.MeetingInvite(meeting_id=id, status=status.status)

@app.patch(
    "/meetings/{id}",
    response_description="Update a meeting",
    response_model=models.MeetingModel,
    response_model_by_alias=False,
)
async def update_meeting(id: str, meeting: schemas.UpdateMeeting = Body(...)):
    meeting_dict = {
        k: v for k, v in meeting.model_dump(by_alias=True).items() if v is not None
    }

    if len(meeting_dict) >= 1:
        update_result = await meetings_collection.find_one_and_update(
            {"_id": ObjectId(id)},
            {"$set": meeting_dict},
            return_document=ReturnDocument.AFTER,
        )
        if update_result is not None:
            return update_result
        else:
            raise HTTPException(status_code=404, detail=f"meeting {id} not found")

    if (existing_meeting := await meetings_collection.find_one({"_id": id})) is not None:
        return existing_meeting

    raise HTTPException(status_code=404, detail=f"meeting {id} not found")

@app.delete(
    "/meetings/{id}", 
    response_description="Delete a meeting"
)
async def delete_meeting(id: str):
    delete_result = await meetings_collection.delete_one({"_id": ObjectId(id)})

    if delete_result.deleted_count == 1:
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    raise HTTPException(status_code=404, detail=f"meeting {id} not found")


# ********** Utils **********

async def get_user(user_id: str) -> dict:
    user_found = await user_collection.find_one({"_id": ObjectId(user_id)})
    if user_found is None:
        raise HTTPException(status_code=404, detail=f"user {user_id} not found")
    return user_found

async def get_meeting(meeting_id: str) -> dict:
    meeting_found = await meetings_collection.find_one({"_id": ObjectId(meeting_id)})
    if meeting_found is None:
        raise HTTPException(status_code=404, detail=f"meeting {meeting_id} not found")
    return meeting_found

async def meeting_in_user(user_id: str, meeting_id: str, status: str) -> dict:
    user_found = await get_user(user_id)
    await get_meeting(meeting_id)
    if user_found.get("meetings") is None:
        user_found["meetings"] = []
    if (status == models.MeetingStatus.needs_acceptance.value):
        user_found["meetings"].append({"meeting_id": meeting_id, "status": status})
    else:
        for meeting in user_found["meetings"]:
            if meeting["meeting_id"] == meeting_id:
                meeting["status"] = status
                break
    await user_collection.update_one(
        {"_id": user_found["_id"]},
        {"$set": {"meetings": user_found["meetings"]}}
    )
    return user_found

async def participant_in_meeting(user_id: str, meeting_id: str, status: str) -> dict:
    meeting_found = await get_meeting(meeting_id)
    await get_user(user_id)
    if meeting_found.get("participants") is None:
        meeting_found["participants"] = []
    if (status == models.MeetingStatus.needs_acceptance.value):
        meeting_found["participants"].append({"user_id": user_id, "status": status})
    else:
        for participant in meeting_found["participants"]:
            if participant["user_id"] == user_id:
                participant["status"] = status
                break
    await meetings_collection.update_one(
        {"_id": meeting_found["_id"]},
        {"$set": {"participants": meeting_found["participants"]}}
    )
    return meeting_found

def check_status(status: str) -> bool:
    if (status not in models.MeetingStatus.__members__):
        raise HTTPException(status_code=400, detail="Invalid status")
    return True

# ********** Groups **********

@app.post(
    "/groups/",
    response_description="Create new group",
    response_model=models.GroupModel,
    status_code=status.HTTP_201_CREATED,
    response_model_by_alias=False,
)
async def createGroup(group: schemas.CreateGroupSchema = Body(...)):

    new_group = await group_collection.insert_one(
        group.model_dump(by_alias=True, exclude={"id"})
    )
    created_group = await group_collection.find_one({"_id": new_group.inserted_id})
    return created_group

@app.get(
    "/groups/",
    response_description="List all groups",
    response_model=models.GroupCollection,
    response_model_by_alias=False,
)
async def list_groups():
    return models.GroupCollection(groups=await group_collection.find().to_list(1000))

@app.get(
    "/groups/{id}",
    response_description="Get a single group",
    response_model=models.GroupModel,
    response_model_by_alias=False,
)
async def show_group(id: str):
    if (group := await group_collection.find_one({"_id": ObjectId(id)})) is not None:
        return group

    raise HTTPException(status_code=404, detail=f"group {id} not found")


@app.put(
    "/groups/{id}",
    response_description="Update a group",
    response_model=models.GroupModel,
    response_model_by_alias=False,
)
async def update_group(id: str, group: models.UpdateGroupModel = Body(...)):
    group_dict = {
        k: v for k, v in group.model_dump(by_alias=True).items() if v is not None
    }

    if len(group_dict) >= 1:
        update_result = await group_collection.find_one_and_update(
            {"_id": ObjectId(id)},
            {"$set": group_dict},
            return_document=ReturnDocument.AFTER,
        )
        if update_result is not None:
            return update_result
        else:
            raise HTTPException(status_code=404, detail=f"group {id} not found")

    if (existing_group := await group_collection.find_one({"_id": id})) is not None:
        return existing_group

    raise HTTPException(status_code=404, detail=f"group {id} not found")


@app.delete(
    "/groups/{id}", 
    response_description="Delete a group"
)
async def delete_group(id: str):
    delete_result = await group_collection.delete_one({"_id": ObjectId(id)})

    if delete_result.deleted_count == 1:
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    raise HTTPException(status_code=404, detail=f"group {id} not found")