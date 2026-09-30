// Fill out your copyright notice in the Description page of Project Settings.
#include "Functions/OSCT_Parsing.h"

#include "OSCManager.h"
#include "OSCToolsetLog.h"

#include "Functions/OSCT_Manager.h"


bool UOSCT_Parsing::GetMessagePackLength(const FOSCMessage& InMessage, FOSCT_PackData& OutData)
{
	//The component length is how many parts each component has, for example a VEC3 is 3 Components.
	//ComponentLength+1 is each element of the pack (KEY+Values)
	//The pack structure expects a string / key before the list of components, so that is why we divide by ComponentLength+1
	//InMessage Argument Length / (ComponentLength+1)
	int32 FoundLength = 0;
	if (UOSCManager::GetInt32(InMessage, 0, FoundLength))
	{
		if (FoundLength > 0)
		{
			OutData.Length = FoundLength;
			// OutData.TotalLength = (OutData.Length * OutData.ComponentLength) + (OutData.Length + 1);
			// UE_LOG(OSCToolset, Warning, TEXT("Pack Data length: %d total: %d ComponentLength: %d"), OutData.Length, OutData.TotalLength, OutData.ComponentLength);
			return true;
		}
	}
	return false;
}

int32 UOSCT_Parsing::GetKeyIndex(const int32 Index, const FOSCT_PackData& InData)
{
	return (Index * (InData.ComponentLength + 1)) + 1;
}


//Single
bool UOSCT_Parsing::TryGetEvent(const FOSCMessage& InMessage, bool& OutValue)
{
	//Events are like a trigger, no need to parse the value.
	return true;
}

bool UOSCT_Parsing::TryGetBool(const FOSCMessage& InMessage, bool& OutValue)
{
	bool Value = false;
	const bool bSuccess = UOSCManager::GetBool(InMessage, 0, Value);
	if (bSuccess)
	{
		OutValue = Value;
		return true;
	}
	return false;
}

bool UOSCT_Parsing::TryGetFloat(const FOSCMessage& InMessage, float& OutValue)
{
	float X=0.0f;
	
	const bool bSuccess = UOSCManager::GetFloat(InMessage, 0, X);
	if (bSuccess)
	{
		OutValue = X;
		return true;
	}
	return false;
}

bool UOSCT_Parsing::TryGetInteger(const FOSCMessage& InMessage, int32& OutValue)
{
	int32 Value = 0;
	const bool bSuccess = UOSCManager::GetInt32(InMessage, 0, Value);
	if (bSuccess)
	{
		OutValue = Value;
		return true;
	}
	return false;
}

bool UOSCT_Parsing::TryGetVector2(const FOSCMessage& InMessage, FVector2D& OutValue)
{
	float X=0.0f, Y=0.0f;
	
	const bool bSuccess = UOSCManager::GetFloat(InMessage, 0, X) &&
		UOSCManager::GetFloat(InMessage, 1, Y);
	if (bSuccess)
	{
		OutValue = FVector2D(X, Y);
		return true;
	}
	return false;
}
bool UOSCT_Parsing::TryGetVector3(const FOSCMessage& InMessage, FVector& OutValue)
{
	float X=0.0f, Y=0.0f, Z=0.0f;

	// Aggregate the results. If any return false, the whole thing is false.
	const bool bSuccess = UOSCManager::GetFloat(InMessage, 0, X) &&
		UOSCManager::GetFloat(InMessage, 1, Y) &&
		UOSCManager::GetFloat(InMessage, 2, Z);
	
	if (bSuccess)
	{
		OutValue = FVector(X, Y, Z);
		return true;
	}
	return false;
}
bool UOSCT_Parsing::TryGetRotation(const FOSCMessage& InMessage, FRotator& OutValue)
{
	float X=0.0f, Y=0.0f, Z=0.0f;
	
	// Aggregate the results. If any return false, the whole thing is false.
	const bool bSuccess = UOSCManager::GetFloat(InMessage, 0, X) &&
		UOSCManager::GetFloat(InMessage, 1, Y) &&
		UOSCManager::GetFloat(InMessage, 2, Z);
	
	if (bSuccess)
	{
		OutValue = FRotator(X, Y, Z);
		return true;
	}
	return false;
}
bool UOSCT_Parsing::TryGetColor(const FOSCMessage& InMessage, FLinearColor& OutValue)
{
	float R=0.0f, G=0.0f, B=0.0f, A=0.0f;
	
	const bool bSuccess = UOSCManager::GetFloat(InMessage, 0, R) &&
	UOSCManager::GetFloat(InMessage, 1, G) &&
	UOSCManager::GetFloat(InMessage, 2, B) &&
	UOSCManager::GetFloat(InMessage, 3, A);
	
	if (bSuccess)
	{
		OutValue = FLinearColor(R, G, B, A);
		return true;
	}
	return false;
}
bool UOSCT_Parsing::TryGetTransform(const FOSCMessage& InMessage, FTransform& OutValue)
{
	float TX=0.0f, TY=0.0f, TZ=0.0f;
	float RX=0.0f, RY=0.0f, RZ=0.0f;
	float SX=1.0f, SY=1.0f, SZ=1.0f;
	
	const bool bSuccess = UOSCManager::GetFloat(InMessage, 0, TX) &&
		UOSCManager::GetFloat(InMessage, 1, TY) &&
		UOSCManager::GetFloat(InMessage, 2, TZ) &&
		UOSCManager::GetFloat(InMessage, 3, RX) &&
		UOSCManager::GetFloat(InMessage, 4, RY) &&
		UOSCManager::GetFloat(InMessage, 5, RZ) &&
		UOSCManager::GetFloat(InMessage, 6, SX) &&
		UOSCManager::GetFloat(InMessage, 7, SY) &&
		UOSCManager::GetFloat(InMessage, 8, SZ);
		
	if (bSuccess)
	{
		OutValue.SetLocation(FVector(TX, TY, TZ));
		OutValue.SetRotation(FQuat(FRotator(RX, RY, RZ)));
		OutValue.SetScale3D(FVector(SX, SY, SZ));
		return true;
	}
	return false;
}
bool UOSCT_Parsing::TryGetString(const FOSCMessage& InMessage, FString& OutValue)
{
	FString Value;
	
	const bool bSuccess = UOSCManager::GetString(InMessage, 0, Value);
	if (bSuccess)
	{
		OutValue = Value;
		return true;
	}
	return false;
}
bool UOSCT_Parsing::TryGetNotes(const FOSCMessage& InMessage, FOSCT_Note& OutValue)
{
	int32 Pitch=0, Velocity=0, Voices=0;
	
	const bool bSuccess = UOSCManager::GetInt32(InMessage, 0, Pitch) &&
		UOSCManager::GetInt32(InMessage, 1, Velocity) &&
		UOSCManager::GetInt32(InMessage, 2, Voices);
	
	if (bSuccess)
	{
		OutValue = FOSCT_Note(Pitch, Velocity, Voices);
		return true;
	}
	return false;
}

//Packs
bool UOSCT_Parsing::TryGetEventPack(const FOSCMessage& InMessage, TMap<FString, bool>& OutMap)
{
	return TryGetGenericPack<bool>(
		InMessage, 
		OutMap, 
		EOSCT_RouteType::EVENT_PACK, 
		[](const FOSCMessage& Msg, int32 StartIdx, bool& OutVal) {
			return UOSCManager::GetBool(Msg, StartIdx, OutVal);
		});
}

bool UOSCT_Parsing::TryGetBoolPack(const FOSCMessage& InMessage, TMap<FString, bool>& OutMap)
{
	return TryGetGenericPack<bool>(
	InMessage, 
	OutMap, 
	EOSCT_RouteType::BOOL_PACK,
	[](const FOSCMessage& Msg, int32 StartIdx, bool& OutVal) {
		return UOSCManager::GetBool(Msg, StartIdx, OutVal);
	});
}

bool UOSCT_Parsing::TryGetFloatPack(const FOSCMessage& InMessage, TMap < FString, float >& OutMap)
{
	return TryGetGenericPack<float>(
		InMessage, 
		OutMap, 
		EOSCT_RouteType::FLOAT_PACK, 
		[](const FOSCMessage& Msg, int32 StartIdx, float& OutVal) {
			return UOSCManager::GetFloat(Msg, StartIdx, OutVal);
		});
}

bool UOSCT_Parsing::TryGetIntegerPack(const FOSCMessage& InMessage, TMap<FString, int32>& OutMap)
{
	return TryGetGenericPack<int32>(
	InMessage, 
	OutMap, 
	EOSCT_RouteType::INT_PACK, 
	[](const FOSCMessage& Msg, int32 StartIdx, int32& OutVal) {
		return UOSCManager::GetInt32(Msg, StartIdx, OutVal);
	});
}

bool UOSCT_Parsing::TryGetVector2Pack(const FOSCMessage& InMessage, TMap<FString, FVector2D>& OutMap)
{
	return TryGetGenericPack<FVector2D>(
		InMessage, 
		OutMap, 
		EOSCT_RouteType::VEC2_PACK, // Use your Event route type here
		[](const FOSCMessage& Msg, int32 StartIdx, FVector2D& OutVal) {
			float X=0.0f, Y=0.0f;
			bool bOk = UOSCManager::GetFloat(Msg, StartIdx, X) && 
					   UOSCManager::GetFloat(Msg, StartIdx + 1, Y); 
			if (bOk) OutVal = FVector2D(X, Y);
			return bOk;
		});
}
bool UOSCT_Parsing::TryGetVector3Pack(const FOSCMessage& InMessage, TMap<FString, FVector>& OutMap)
{
	return TryGetGenericPack<FVector>(
		InMessage, 
		OutMap, 
		EOSCT_RouteType::VEC3_PACK, 
		[](const FOSCMessage& Msg, int32 StartIdx, FVector& OutVal) {
			float X=0.0f, Y=0.0f, Z=0.0f;
			bool bOk = UOSCManager::GetFloat(Msg, StartIdx, X) && 
					   UOSCManager::GetFloat(Msg, StartIdx + 1, Y) && 
					   UOSCManager::GetFloat(Msg, StartIdx + 2, Z);
			if (bOk) OutVal = FVector(X, Y, Z);
			return bOk;
		});
}
bool UOSCT_Parsing::TryGetRotationPack(const FOSCMessage& InMessage, TMap<FString, FRotator>& OutMap)
{
	return TryGetGenericPack<FRotator>(
		InMessage, 
		OutMap, 
		EOSCT_RouteType::VEC3_PACK, 
		[](const FOSCMessage& Msg, int32 StartIdx, FRotator& OutVal) {
			float X=0.0f, Y=0.0f, Z=0.0f;
			bool bOk = UOSCManager::GetFloat(Msg, StartIdx, X) && 
					   UOSCManager::GetFloat(Msg, StartIdx + 1, Y) && 
					   UOSCManager::GetFloat(Msg, StartIdx + 2, Z);
			if (bOk) OutVal = FRotator(X, Y, Z);
			return bOk;
		});

}
bool UOSCT_Parsing::TryGetColorPack(const FOSCMessage& InMessage, TMap<FString, FLinearColor>& OutMap)
{
	return TryGetGenericPack<FLinearColor>(
	InMessage, 
	OutMap, 
	EOSCT_RouteType::COLOR_PACK, 
	[](const FOSCMessage& Msg, int32 StartIdx, FLinearColor& OutVal) {
		float R=0.0f, G=0.0f, B=0.0f, A=0.0f;
		bool bOk = UOSCManager::GetFloat(Msg, StartIdx, R) && 
				   UOSCManager::GetFloat(Msg, StartIdx + 1, G) &&
				   UOSCManager::GetFloat(Msg, StartIdx + 2, B) &&
				   UOSCManager::GetFloat(Msg, StartIdx + 3, A);
		if (bOk) {
			OutVal = FLinearColor(R, G, B, A);
		}
		return bOk;
	});
}
bool UOSCT_Parsing::TryGetTransformPack(const FOSCMessage& InMessage, TMap<FString, FTransform>& OutMap)
{
	return TryGetGenericPack<FTransform>(
		InMessage, 
		OutMap, 
		EOSCT_RouteType::TRANSFORM_PACK, 
		[](const FOSCMessage& Msg, int32 StartIdx, FTransform& OutVal) {
			float TX=0.0f, TY=0.0f, TZ=0.0f, RX=0.0f, RY=0.0f, RZ=0.0f, SX=1.0f, SY=1.0f, SZ=1.0f;
			bool bOk = UOSCManager::GetFloat(Msg, StartIdx, TX) && 
					   UOSCManager::GetFloat(Msg, StartIdx + 1, TY) &&
					   UOSCManager::GetFloat(Msg, StartIdx + 2, TZ) &&
					   UOSCManager::GetFloat(Msg, StartIdx + 3, RX) &&
					   UOSCManager::GetFloat(Msg, StartIdx + 4, RY) &&
					   UOSCManager::GetFloat(Msg, StartIdx + 5, RZ) &&
					   UOSCManager::GetFloat(Msg, StartIdx + 6, SX) &&
					   UOSCManager::GetFloat(Msg, StartIdx + 7, SY) &&
					   UOSCManager::GetFloat(Msg, StartIdx + 8, SZ);
        
			if (bOk) {
				OutVal = FTransform(FRotator(RX, RY, RZ), FVector(TX, TY, TZ), FVector(SX, SY, SZ));
			}
			return bOk;
		});
}
bool UOSCT_Parsing::TryGetStringPack(const FOSCMessage& InMessage, TArray<FString>& OutValue)
{
	UOSCManager::GetAllStrings(InMessage, OutValue);
	return true;
}