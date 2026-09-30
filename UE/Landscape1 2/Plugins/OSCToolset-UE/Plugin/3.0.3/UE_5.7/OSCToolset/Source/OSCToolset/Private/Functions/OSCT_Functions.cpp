// Fill out your copyright notice in the Description page of Project Settings.

#include "Functions/OSCT_Functions.h"

#include "OSCManager.h"
#include "OSCClient.h"
#include "OSCAddress.h"
#include "OSCT_ETypes.h"
#include "OSCT_Modules.h"
#include "OSCToolsetLog.h"


template<typename T>
FString UOSCT_Functions::GetEnumString(T EnumValue)
{
	const UEnum* EnumPtr = StaticEnum<T>();
	if (!EnumPtr || !EnumPtr->IsValidLowLevel()) return TEXT("INVALID");
	return EnumPtr->GetNameStringByValue(static_cast<int64>(EnumValue));
}

// EOSCT_ModuleType UOSCT_Functions::ConvertSenderTypeToModuleType(EOSCT_SenderType InSender)
// {
// 	switch (InSender)
// 	{
// 	case EOSCT_SenderType::EVENT:  return EOSCT_ModuleType::EVENT;
// 	case EOSCT_SenderType::FLOAT:  return EOSCT_ModuleType::FLOAT;
// 	case EOSCT_SenderType::STRING: return EOSCT_ModuleType::STRING;
// 	default:                       return EOSCT_ModuleType::EVENT;
// 	}
// }

// EOSCT_SenderType UOSCT_Functions::ConvertModuleTypeToSenderType(EOSCT_ModuleType InModule)
// {
// 	switch (InModule)
// 	{
// 	case EOSCT_ModuleType::EVENT:  return EOSCT_SenderType::EVENT;
// 	case EOSCT_ModuleType::FLOAT:  return EOSCT_SenderType::FLOAT;
// 	case EOSCT_ModuleType::STRING: return EOSCT_SenderType::STRING;
// 	default:                       return EOSCT_SenderType::EVENT;
// 	}
// }

EOSCT_RouteType UOSCT_Functions::ConvertModuleTypeToRouteType(EOSCT_ModuleType InModule, const bool bPack)
{
	switch (InModule)
	{
	case EOSCT_ModuleType::EVENT:  
		return bPack ? EOSCT_RouteType::EVENT_PACK : EOSCT_RouteType::EVENT;
	case EOSCT_ModuleType::BOOL:  
		return bPack ? EOSCT_RouteType::BOOL_PACK : EOSCT_RouteType::BOOL;
	case EOSCT_ModuleType::FLOAT:  
		return bPack ? EOSCT_RouteType::FLOAT_PACK : EOSCT_RouteType::FLOAT;
	case EOSCT_ModuleType::INT:  
		return bPack ? EOSCT_RouteType::INT_PACK : EOSCT_RouteType::INT;
	case EOSCT_ModuleType::VEC2:
		return bPack ? EOSCT_RouteType::VEC2_PACK : EOSCT_RouteType::VEC2;
	case EOSCT_ModuleType::VEC3:   
		return bPack ? EOSCT_RouteType::VEC3_PACK  : EOSCT_RouteType::VEC3;	
	case EOSCT_ModuleType::COLOR:   
		return bPack ? EOSCT_RouteType::COLOR_PACK  : EOSCT_RouteType::COLOR;		
	case EOSCT_ModuleType::ROTATION:   
		return bPack ? EOSCT_RouteType::ROTATION_PACK  : EOSCT_RouteType::ROTATION;		
	case EOSCT_ModuleType::TRANSFORM:   
		return bPack ? EOSCT_RouteType::TRANSFORM_PACK  : EOSCT_RouteType::TRANSFORM;		
	case EOSCT_ModuleType::STRING:   
		return bPack ? EOSCT_RouteType::STRING_PACK  : EOSCT_RouteType::STRING;		
	case EOSCT_ModuleType::NOTE:   
		return EOSCT_RouteType::NOTE; //No packs for notes, for now?	

	default:                       
		return EOSCT_RouteType::EVENT;
	}

}

int32 UOSCT_Functions::GetComponentLength(EOSCT_RouteType Type)
{
	switch (Type)
	{
	case EOSCT_RouteType::EVENT:
	case EOSCT_RouteType::EVENT_PACK:
	case EOSCT_RouteType::BOOL:
	case EOSCT_RouteType::BOOL_PACK:
	case EOSCT_RouteType::FLOAT:
	case EOSCT_RouteType::FLOAT_PACK:
	case EOSCT_RouteType::INT:
	case EOSCT_RouteType::INT_PACK:
		return 1;
	case EOSCT_RouteType::VEC2:
	case EOSCT_RouteType::VEC2_PACK:
		return 2;
	case EOSCT_RouteType::VEC3:
	case EOSCT_RouteType::VEC3_PACK:
	case EOSCT_RouteType::ROTATION:
	case EOSCT_RouteType::ROTATION_PACK:
		return 3;
	case EOSCT_RouteType::COLOR:
	case EOSCT_RouteType::COLOR_PACK:
		return 4;
	case EOSCT_RouteType::TRANSFORM:
	case EOSCT_RouteType::TRANSFORM_PACK:
		return 9;
	default:
		return -1;
	}
}

FString UOSCT_Functions::CleanupAddress(const FString& InAddress)
{
	FString CleanAddress = InAddress;
	CleanAddress.RemoveFromStart(TEXT("/"));
	return CleanAddress;
}

bool UOSCT_Functions::FormatAddress(const EOSCT_Role& Role, const EOSCT_ModuleType& ModuleType, const bool bPack, const FString& Address, FString& OutAddress)
{
	if (Address.IsEmpty()) return false;

	OutAddress.Reset(); 

	FString RoleStr = GetEnumString(Role).ToUpper().Left(1);
	FString ModuleStr = GetEnumString(ModuleType).ToUpper();
   
	OutAddress.Append(TEXT("/OSCT/"));
	OutAddress.Append(RoleStr);
	OutAddress.AppendChar('/');
	OutAddress.Append(ModuleStr);
    
	if (bPack)
	{
		OutAddress.Append(TEXT("/p"));
	}

	OutAddress.AppendChar('/');

	if (Address.StartsWith(TEXT("/")))
	{
		OutAddress.Append(Address.RightChop(1));
	}
	else
	{
		OutAddress.Append(Address);
	}

	return true;
}

FOSCMessage UOSCT_Functions::CreateStateUpdate(
	UObject* Context,
	const FString& Address,
	const FString& FormattedAddress,
	const EOSCT_Role& Role,
	const EOSCT_ModuleType& ModuleType, 
	const bool Pack,
	const bool bIsConnecting)
{
	FOSCMessage Msg;
	FString Path = bIsConnecting ? TEXT("/OSCT/module_connected") : TEXT("/OSCT/module_disconnected");
	
	// Helper to add "Key%Value" strings quickly
	auto AddKVP = [&](FString Key, FString Value) {
		UOSCManager::AddString(Msg, Key + "%" + Value);
	};
	// 3. Populate Data
	if (Context)
	{
		AddKVP(TEXT("Name"), Context->GetName());
		AddKVP(TEXT("Class"), Context->GetClass()->GetName());
	} else
	{
		AddKVP(TEXT("Name"), "");
		AddKVP(TEXT("Class"), "");
	}
	AddKVP(TEXT("Address"), CleanupAddress(Address));
	AddKVP(TEXT("Formatted Address"), FormattedAddress);
	AddKVP(TEXT("Role Type"), UEnum::GetDisplayValueAsText(Role).ToString().ToUpper());
	AddKVP(TEXT("ModuleType"), GetEnumString(ModuleType).ToUpper());
	AddKVP(TEXT("Pack"), Pack ? TEXT("true") : TEXT("false"));
	UOSCManager::SetOSCMessageAddress(Msg, UOSCManager::ConvertStringToOSCAddress(Path));
	return Msg;
}

void UOSCT_Functions::SendReceiverStateUpdate(const TArray<UOSCClient*>& Clients, const FOSCT_Receiver& Data, UObject* Context, bool bIsConnecting)
{
	for (UOSCClient* Client : Clients)
	{
		if (Client) {
			FOSCMessage Msg = CreateStateUpdate(
				Context,
				Data.Address,
				Data.FormattedAddress,
				Data.Role,
				Data.ModuleType,
				Data.Pack,
				bIsConnecting
			);
			Client->SendOSCMessage(Msg);
		}
	}
}

void UOSCT_Functions::SendSenderStateUpdate(const TArray<UOSCClient*>& Clients, const FOSCT_Sender& Data, UObject* Context,	bool bIsConnecting)
{
	for (UOSCClient* Client : Clients)
	{
		if (Client)
		{
			FOSCMessage Msg = CreateStateUpdate(
				Context,
				Data.Address,
				Data.FormattedAddress,
				Data.Role,
				Data.ModuleType,
				false,
				bIsConnecting
			);
			Client->SendOSCMessage(Msg);
		}
	}
}

FColor UOSCT_Functions::GetModuleDebugColor(const EOSCT_ModuleType& ModuleType)
{
	FColor DebugColor = FColor::White;
	switch (ModuleType)
	{
	case EOSCT_ModuleType::EVENT:
		DebugColor = FColor(255, 0, 100);
		break;
	case EOSCT_ModuleType::BOOL:
		DebugColor = FColor(255, 0, 0);
		break;
	case EOSCT_ModuleType::FLOAT:
		DebugColor = FColor(80, 255, 0);
		break;
	case EOSCT_ModuleType::INT:
		DebugColor = FColor(50, 255, 150);
		break;
	case EOSCT_ModuleType::VEC2:
		DebugColor = FColor(0, 200, 255);
		break;
	case EOSCT_ModuleType::VEC3:
		DebugColor = FColor(230, 200, 0);
		break;
	case EOSCT_ModuleType::COLOR:
		DebugColor = FColor(0, 50, 255);
		break;
	case EOSCT_ModuleType::TRANSFORM:
		DebugColor = FColor(255, 127, 0);
		break;
	case EOSCT_ModuleType::STRING:
		DebugColor = FColor(230, 76, 255);
		break;
	case EOSCT_ModuleType::ROTATION:
		DebugColor = FColor(127, 140, 255);
		break;
	case EOSCT_ModuleType::NOTE:
		DebugColor = FColor(80, 80, 255);
		break;
	}
	return DebugColor;
}

void UOSCT_Functions::DisplayDebug(
		const FString& FormattedAddress, 
		const EOSCT_ModuleType& ModuleType,
		const FOSCT_ModuleDebug& Debug, 
		const FString& Message
		)
{
	// Use a hash of the address as a KEY so the message updates in place instead of scrolling
	uint64 Key = GetTypeHash(FormattedAddress);
	FColor Color = (Debug.DebugColor != FColor::White) 
				   ? Debug.DebugColor
				   : GetModuleDebugColor(ModuleType);

	if (GEngine && Debug.PrintOnScreen)
	{
		GEngine->AddOnScreenDebugMessage(Key, Debug.DebugDuration, Color, Message);
	}
    
	if (Debug.PrintOnLog)
	{
		UE_LOG(OSCToolset, Log, TEXT("%s"), *Message);
	}
}