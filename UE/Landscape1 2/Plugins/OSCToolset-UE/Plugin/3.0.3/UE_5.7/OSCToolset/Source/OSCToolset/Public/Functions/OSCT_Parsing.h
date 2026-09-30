// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "OSCManager.h"
#include "OSCT_ETypes.h"
#include "Functions/OSCT_Functions.h"
#include "OSCT_Parsing.generated.h"


USTRUCT()
struct FOSCT_PackData
{
	GENERATED_BODY()
	
	UPROPERTY()
	int32 Length = 0;
	
	UPROPERTY()
	int32 TotalLength = 0;
	
	UPROPERTY()
	EOSCT_RouteType Type = EOSCT_RouteType::EVENT;
	
	UPROPERTY()
	int32 ComponentLength = -1;
	// Default constructor (required by UE)
	FOSCT_PackData() {}
	
	// Custom constructor
	FOSCT_PackData(EOSCT_RouteType InType) : Type(InType)
	{
		ComponentLength = UOSCT_Functions::GetComponentLength(Type);
	}
};
/**
 * 
 */
UCLASS()
class OSCTOOLSET_API UOSCT_Parsing : public UBlueprintFunctionLibrary
{
	GENERATED_BODY()
private:
	static bool GetMessagePackLength(const FOSCMessage& InMessage, FOSCT_PackData& OutData);
	static int32 GetKeyIndex(const int32 Index, const FOSCT_PackData& InData);
	// static int32 GetPackTotalLength(const int32 Length, const int32 ComponentLength);
public:
	//Template
	template<typename ValueType, typename ExtractFunc>
	static bool TryGetGenericPack(const FOSCMessage& InMessage, TMap<FString, ValueType>& OutMap, EOSCT_RouteType RouteType, ExtractFunc ExtractValue)
		{
			FOSCT_PackData Data(RouteType);
			if (!GetMessagePackLength(InMessage, Data)) return false;

			FString Key;
			for (int32 i = 0; i < Data.Length; ++i)
			{
				int32 KeyIndex = GetKeyIndex(i, Data);
				if (UOSCManager::GetString(InMessage, KeyIndex, Key))
				{
					ValueType TempValue;
					if (ExtractValue(InMessage, KeyIndex + 1, TempValue))
					{
						OutMap.FindOrAdd(Key) = TempValue;
					}
				}
			}
			return OutMap.Num() > 0;
		}
	
	//Single
	static bool TryGetEvent(const FOSCMessage& InMessage, bool& OutValue);
	static bool TryGetBool(const FOSCMessage& InMessage, bool& OutValue);
	static bool TryGetFloat(const FOSCMessage& InMessage, float& OutValue);
	static bool TryGetInteger(const FOSCMessage& InMessage, int32& OutValue);
	static bool TryGetVector2(const FOSCMessage& InMessage, FVector2D& OutValue);
	static bool TryGetVector3(const FOSCMessage& InMessage, FVector& OutValue);
	static bool TryGetRotation(const FOSCMessage& InMessage, FRotator& OutValue);
	static bool TryGetColor(const FOSCMessage& InMessage, FLinearColor& OutValue);
	static bool TryGetTransform(const FOSCMessage& InMessage, FTransform& OutValue);
	static bool TryGetString(const FOSCMessage& InMessage, FString& OutValue);
	static bool TryGetNotes(const FOSCMessage& InMessage, FOSCT_Note& OutValue);
	//Packs
	static bool TryGetEventPack(const FOSCMessage& InMessage, TMap < FString, bool>& OutMap);
	static bool TryGetBoolPack(const FOSCMessage& InMessage, TMap < FString, bool>& OutMap);
	static bool TryGetFloatPack(const FOSCMessage& InMessage, TMap < FString, float >& OutMap);
	static bool TryGetIntegerPack(const FOSCMessage& InMessage, TMap < FString, int32 >& OutMap);
	static bool TryGetVector2Pack(const FOSCMessage& InMessage, TMap < FString, FVector2D >& OutMap);
	static bool TryGetVector3Pack(const FOSCMessage& InMessage, TMap < FString, FVector >& OutMap);
	static bool TryGetRotationPack(const FOSCMessage& InMessage, TMap < FString, FRotator >& OutMap);
	static bool TryGetColorPack(const FOSCMessage& InMessage, TMap < FString, FLinearColor >& OutMap);
	static bool TryGetTransformPack(const FOSCMessage& InMessage, TMap < FString, FTransform >& OutMap);
	static bool TryGetStringPack(const FOSCMessage& InMessage, TArray<FString>& OutValue);
	
};
