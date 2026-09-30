// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include <string>

#include "CoreMinimal.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "Engine/Engine.h" //Required for GEngine
#include "OSCT_ETypes.h"
#include "OSCT_Modules.h"

#include "OSCT_Functions.generated.h"

namespace OSCT_DebugString
{
	// Simple helpers for common OSC types
	static FString ToString(const FString& S) { return S; }
	static FString ToString(const FName& N)   { return N.ToString(); }
	static FString ToString(int32 I)          { return FString::FromInt(I); }
	static FString ToString(bool B)           { return B ? TEXT("True") : TEXT("False"); }
	
	
	static FString ToString(float V)          { return FString::SanitizeFloat(V); }
	static FString ToString(const FVector2D& V)  { return V.ToString(); }
	static FString ToString(const FVector& V)  { return V.ToString(); }
	static FString ToString(const FLinearColor& C) { return C.ToString(); }
	static FString ToString(const FRotator& R) { return R.ToString(); }
	static FString ToString(const FTransform& R) { return R.ToString(); }
    static FString ToString(const FOSCT_Note& N) { return N.ToString(); }
	
	// For the Maps/Arrays that were causing trouble
	template<typename T>
	static FString ToString(const TArray<T>& A) { return FString::Printf(TEXT("Array of %d items"), A.Num()); }
    
	template<typename K, typename V>
	static FString ToString(const TMap<K, V>& M) { return FString::Printf(TEXT("Pack of %d items"), M.Num()); }
	
	template<typename T>
	static FString ToString(const T& Value) 
	{ 
		return TEXT("{Unknown Type}"); 
	}
}

UCLASS()
class OSCTOOLSET_API UOSCT_Functions : public UBlueprintFunctionLibrary
{
	GENERATED_BODY()

public:
	// static void DisplayDebug(const FOSCT_Receiver& Module, const FString& Message);
	static void DisplayDebug(
		const FString& FormattedAddress, 
		const EOSCT_ModuleType& ModuleType,
		const FOSCT_ModuleDebug& Debug, 
		const FString& Message);
	
	/** Safely converts any Enum to a string without crashing the Editor */
	template<typename T>
	static FString GetEnumString(T EnumValue);

	// static EOSCT_ModuleType ConvertSenderTypeToModuleType(EOSCT_SenderType InSender);
	// static EOSCT_SenderType ConvertModuleTypeToSenderType(EOSCT_ModuleType InModule);
	static EOSCT_RouteType ConvertModuleTypeToRouteType(EOSCT_ModuleType InModule, const bool bPack);
	static int32 GetComponentLength(EOSCT_RouteType Type);
	
	static FString CleanupAddress(const FString& InAddress);
	
	UFUNCTION(BlueprintCallable, Category="OSCToolset")
	static bool FormatAddress(const EOSCT_Role& Role, const EOSCT_ModuleType& ModuleType, const bool bPack, const FString& Address, FString& OutAddress);
	// static bool FormatAddress(const FOSCT_Module& Module, FString& OutAddress);
	
	UFUNCTION()
	static FOSCMessage CreateStateUpdate(
		UObject* Context,
		const FString& Address,
		const FString& FormattedAddress,
		const EOSCT_Role& Role,
		const EOSCT_ModuleType& ModuleType, 
		const bool Pack,
		const bool bIsConnecting
	);
	UFUNCTION(BlueprintCallable, Category = "OSCToolset|Networking")
	static void SendReceiverStateUpdate(const TArray<UOSCClient*>& Clients, const FOSCT_Receiver& Data, UObject* Context, bool bIsConnecting);
	UFUNCTION(BlueprintCallable, Category = "OSCToolset|Networking")
	static void SendSenderStateUpdate(const TArray<UOSCClient*>& Clients, const FOSCT_Sender& Data, UObject* Context, bool bIsConnecting);

	
	//Debug Template
	template<typename TLink, typename TValue>
	static void DebugReceiverLink(const TLink& Link, const TValue& Value)
	{
		if (!Link.Data.Debug.PrintOnLog && !Link.Data.Debug.PrintOnScreen) return;
		
		// Use our custom stringifier
		FString ValueStr = OSCT_DebugString::ToString(Value);
		
		FString FullMessage = FString::Printf(TEXT("%s: %s"), 
			*Link.Data.FormattedAddress, 
			*ValueStr);

		DisplayDebug(Link.Data.FormattedAddress, Link.Data.ModuleType, Link.Data.Debug, FullMessage);
	}
	//Debug Template
	template<typename TSender, typename TValue>
	static void DebugSender(const TSender& Sender, const TValue& Value)
	{
		if (!Sender.Debug.PrintOnLog && !Sender.Debug.PrintOnScreen) return;
		
		// Use our custom stringifier
		FString ValueStr = OSCT_DebugString::ToString(Value);
		
		FString FullMessage = FString::Printf(TEXT("%s: %s"), 
			*Sender.FormattedAddress, 
			*ValueStr);

		DisplayDebug(Sender.FormattedAddress, Sender.ModuleType, Sender.Debug, FullMessage);
	}
	
	UFUNCTION(BlueprintCallable, Category = "OSCToolset|Debug")
	static FColor GetModuleDebugColor(const EOSCT_ModuleType& ModuleType);
};
