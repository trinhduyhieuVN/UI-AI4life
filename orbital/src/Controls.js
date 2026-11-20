import React from 'react';
import { Modal, Pressable, ScrollView, View } from 'react-native';
import { clock, dateLabel } from './market';
import { Button, C, Icon, mono, row, T } from './ui';
import { Notifications } from './Notifications';
import { NewsTicker } from './NewsTicker';

export const card = {backgroundColor:'#101b2a', borderColor:'#344051', borderWidth:1, borderRadius:16};
export function Header({small,market}) {
  return <View style={{backgroundColor:'#09101ccd',borderBottomWidth:1,borderColor:'#a4bfdd20'}}>
    <View style={[row,{height:small?56:68,paddingHorizontal:small?14:'4%',gap:small?12:24}]}>
    <View style={[row,{gap:7}]}><Icon name="orbit" color={C.gold} size={small?26:33}/><T size={small?21:26} weight="700" style={{letterSpacing:-1}}>Nev<T size={small?21:26} weight="700" color={C.gold}>AI</T></T></View>
    <View style={[row,{flexGrow:small?1:0,justifyContent:small?'flex-end':'flex-start',gap:small?12:24,height:'100%'}]}>
      <T size={small?12:14} weight="600">Trang chủ</T>
    </View>
    {!small&&<View style={{flex:1,minWidth:0}}><NewsTicker/></View>}
    <Notifications market={market} small={small}/>
    </View>
    {small&&<View style={{paddingHorizontal:12,paddingBottom:5}}><NewsTicker/></View>}
  </View>;
}

export function ReplayPill({market,onDates,small}) {
  const minute=market.frame?.minute??0;
  return <View pointerEvents="box-none" style={{position:'absolute',bottom:small?14:24,left:0,right:0,alignItems:'center'}}>
    <View style={[row,{backgroundColor:'#0b1421ef',borderWidth:1,borderColor:'#b2c5df39',borderRadius:25,paddingHorizontal:8,paddingVertical:3,gap:small?3:8}]}>
      <Button label={market.playing?'Tạm dừng phiên':'Phát phiên'} disabled={!market.day||!!market.error} onPress={market.toggle} style={{height:36,width:34}}><Icon name={market.playing?'pause':'play'} color={C.gold} size={16}/></Button>
      <Button label="Chọn phiên giao dịch" onPress={onDates} disabled={!market.day} style={{height:36,paddingHorizontal:4}}>
        <Icon name="calendar" size={14}/><T size={12}>{market.day?dateLabel(market.day):'Đang tải'}</T><Icon name="chevron" size={12}/>
      </Button>
      <T size={11} color={C.muted} style={{fontFamily:mono}}>{clock(market.open,minute)} ET</T>
      <View style={{width:1,height:16,backgroundColor:C.line,marginHorizontal:3}}/>
      <Button label={'Tốc độ phát '+market.speed+'×'} onPress={market.cycleSpeed} style={{height:34,minWidth:46,paddingHorizontal:5}}>
        <T size={12} weight="700" color={C.gold}>{market.speed}×</T>
      </Button>
    </View>
  </View>;
}
export function Dialog({children,onClose,small,label}) {
  return <Modal visible transparent animationType="fade" onRequestClose={onClose}><View style={{flex:1,justifyContent:small?'flex-end':'center',alignItems:'center',backgroundColor:'#03070fbb',padding:small?8:22}}>
    <Pressable accessibilityLabel="Đóng" onPress={onClose} style={{position:'absolute',left:0,top:0,right:0,bottom:0}}/>
    <View accessibilityLabel={label} accessibilityViewIsModal style={[card,{maxHeight:'90%',width:'100%',maxWidth:445}]}><ScrollView keyboardShouldPersistTaps="handled">{children}</ScrollView></View>
  </View></Modal>;
}
