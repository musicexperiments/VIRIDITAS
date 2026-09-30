// Copyright (c) 2024, Studio Eusebi Jucgla. All rights reserved 
// MD5: 2245b93ed1bae2e4aff277e6f3ecb8ff


#pragma once

#include "CoreMinimal.h"
#include "Widgets/SCompoundWidget.h"
#include "Widgets/Input/SSpinBox.h"
#include "Widgets/Input/SEditableTextBox.h"
#include "Widgets/Input/SCheckBox.h"
#include "OSCT_Settings.h"
/**
 * 
 */
DECLARE_DELEGATE(FOnReInitOSCT);

class OSCTOOLSET_API SOSCT_Menu : public SCompoundWidget
{
public:
	SLATE_BEGIN_ARGS(SOSCT_Menu) {}
	SLATE_END_ARGS()
	
	FOnReInitOSCT OnReInitOSCT;

	void Construct(const FArguments& InArgs);

private:

	void SaveSettings();
	
	// Helper functions to build UI pieces
	TSharedRef<SWidget> MakeHeaderWidget();
	TSharedRef<SWidget> MakeServerSettingsWidget();
	void RefreshClientList();
	
	//FReply OnSaveSettings();
	FReply OnReinitializeOSCT();
	
	FSlateFontInfo TitleFont = FCoreStyle::GetDefaultFontStyle("Bold", 18); 
	FSlateFontInfo LabelFont = FCoreStyle::GetDefaultFontStyle("Regular", 14);
	
	// TSharedPtr<SEditableTextBox> ServerAddressTextBox;
	// TSharedPtr<SSpinBox<int32>> ServerPortSpinBox;
	// TSharedPtr<SCheckBox> MulticastLoopbackBox;
	//
	// TSharedRef<SWidget> MakeClientEntryWidget(int32 Index, FOSCT_Network& ClientData);
	//
	// TSharedPtr<SEditableTextBox> ClientAddressTextBox;
	// TSharedPtr<SSpinBox<int32>> ClientPortSpinBox;
	//
	// TSharedPtr<SCheckBox> UseLocalIPV4Box;
	
	UOSCT_Settings* Settings;
	TSharedPtr<SVerticalBox> MainContentBox;
	TSharedPtr<SVerticalBox> ClientListBox;

};
