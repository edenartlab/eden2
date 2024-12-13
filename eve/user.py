from bson import ObjectId
from typing import Optional, Literal, List

from .mongo import Document, Collection, get_collection


@Collection("users3")
class User(Document):
    # type of user
    type: Optional[Literal["user", "agent"]] = "user"
    isAdmin: Optional[bool] = False
    deleted: Optional[bool] = False

    # auth settings
    userId: Optional[str] = None
    isWeb2: Optional[bool] = False
    email: Optional[str] = None
    normalizedEmail: Optional[str] = None

    # agent settings
    agent: Optional[ObjectId] = None
    owner: Optional[ObjectId] = None

    # permissions
    featureFlags: Optional[List[str]] = None
    subscriptionTier: Optional[int] = None
    highestMonthlySubscriptionTier: Optional[int] = None

    # profile
    username: str
    userImage: Optional[str] = None

    # origins
    discordId: Optional[str] = None
    discordUsername: Optional[str] = None
    telegramId: Optional[str] = None
    telegramUsername: Optional[str] = None
    farcasterId: Optional[str] = None
    farcasterUsername: Optional[str] = None

    def verify_manna_balance(self, amount: float):
        mannas = get_collection("mannas", db=self.db)
        manna = mannas.find_one({"user": self.id})
        if not manna:
            raise Exception("Mannas not found")
        balance = manna.get("balance") + manna.get("subscriptionBalance", 0)
        if balance < amount:
            raise Exception(
                f"Insufficient manna balance. Need {amount} but only have {balance}"
            )

    def spend_manna(self, amount: float):
        if amount == 0:
            return

        mannas = get_collection("mannas", db=self.db)
        manna = mannas.find_one({"user": self.id})
        if not manna:
            raise Exception("Mannas not found")
        subscription_balance = manna.get("subscriptionBalance", 0)

        # Use subscription balance first
        if subscription_balance > 0:
            subscription_spend = min(subscription_balance, amount)
            mannas.update_one(
                {"user": self.id},
                {"$inc": {"subscriptionBalance": -subscription_spend}},
            )
            amount -= subscription_spend

        # If there's remaining amount, use regular balance
        if amount > 0:
            mannas.update_one({"user": self.id}, {"$inc": {"balance": -amount}})

    def refund_manna(self, amount: float):
        if amount == 0:
            return

        # todo: make it refund to subscription balance first
        mannas = get_collection("mannas", db=self.db)
        mannas.update_one({"user": self.id}, {"$inc": {"balance": amount}})

    @classmethod
    def from_discord(cls, discord_id, discord_username, db="STAGE"):
        discord_id = str(discord_id)
        users = get_collection(cls.collection_name, db=db)
        user = users.find_one({"discordId": discord_id})
        if not user:
            # Find a unique username
            base_username = discord_username
            username = base_username
            counter = 2
            while users.find_one({"username": username}):
                username = f"{base_username}{counter}"
                counter += 1

            new_user = cls(
                db=db,
                discordId=discord_id,
                discordUsername=discord_username,
                username=username,
            )
            new_user.save()
            return new_user
        return cls(**user, db=db)

    @classmethod
    def from_farcaster(cls, farcaster_id, farcaster_username, db="STAGE"):
        farcaster_id = str(farcaster_id)
        users = get_collection(cls.collection_name, db=db)
        user = users.find_one({"farcasterId": farcaster_id})
        if not user:
            # Find a unique username
            base_username = farcaster_username
            username = base_username
            counter = 2
            while users.find_one({"username": username}):
                username = f"{base_username}{counter}"
                counter += 1

            new_user = cls(
                db=db,
                farcasterId=farcaster_id,
                farcasterUsername=farcaster_username,
                username=username,
            )
            new_user.save()
            return new_user
        return cls(**user, db=db)

    @classmethod
    def from_telegram(cls, telegram_id, telegram_username, db="STAGE"):
        telegram_id = str(telegram_id)
        users = get_collection(cls.collection_name, db=db)
        user = users.find_one({"telegramId": telegram_id})
        if not user:
            # Find a unique username
            base_username = telegram_username or f"telegram_{telegram_id}"
            username = base_username
            counter = 2
            while users.find_one({"username": username}):
                username = f"{base_username}{counter}"
                counter += 1

            new_user = cls(
                db=db,
                telegramId=telegram_id,
                telegramUsername=telegram_username,
                username=username,
            )
            new_user.save()
            return new_user
        return cls(**user, db=db)
