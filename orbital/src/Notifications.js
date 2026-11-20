import React, {useMemo, useState} from 'react';
import {Modal, Pressable, ScrollView, View, useWindowDimensions} from 'react-native';
import {useSafeAreaInsets} from 'react-native-safe-area-context';
import {clock, dateLabel, number} from './market';
import {Button, C, Dot, Icon, mono, row, T} from './ui';

function alertIntervals(frame) {
  const alerts = [];
  for (const [symbol, points] of Object.entries(frame?.bySymbol ?? {})) {
    let current;
    for (const point of points) {
      if (!(point.energy > point.threshold)) continue;
      if (current && current.end === point.minute - 1) {
        current.end = point.minute;
        current.peak = Math.max(current.peak, point.energy);
      } else {
        current = {symbol, start:point.minute - 1, end:point.minute, peak:point.energy};
        alerts.push(current);
      }
    }
  }
  return alerts.sort((a,b) => b.end - a.end || b.start - a.start || a.symbol.localeCompare(b.symbol));
}

export function Notifications({market, small}) {
  const [visible, setVisible] = useState(false);
  const alerts = useMemo(() => alertIntervals(market.frame), [market.frame]);
  const {width,height} = useWindowDimensions();
  const insets = useSafeAreaInsets();
  const close = () => setVisible(false);
  const count = alerts.length;
  const top = insets.top + (small ? 60 : 72);
  return <>
    <Pressable testID="notification-bell" accessibilityRole="button" accessibilityLabel={'Thông báo bất thường: '+count}
      accessibilityState={{expanded:visible}} onPress={() => setVisible(true)}
      style={({pressed,hovered}) => ({width:44,height:44,borderRadius:22,alignItems:'center',justifyContent:'center',backgroundColor:pressed||hovered?'#23303d':'transparent'})}>
      <Icon name="bell" size={22} color={C.white}/>
      {count>0&&<View pointerEvents="none" testID="alert-count" style={{position:'absolute',top:1,right:0,minWidth:18,height:18,paddingHorizontal:4,borderRadius:9,alignItems:'center',justifyContent:'center',backgroundColor:'#d33342'}}>
        <T size={10} weight="700" color="#fff">{count}</T>
      </View>}
    </Pressable>
    {visible&&<Modal transparent animationType="fade" visible onRequestClose={close}>
      <View style={{flex:1,alignItems:'flex-end',paddingTop:top,paddingRight:small?10:Math.round(width*.04)}}>
        <Pressable accessible={false} testID="notification-backdrop" onPress={close} style={{position:'absolute',top:0,left:0,right:0,bottom:0,backgroundColor:'#03081255'}}/>
        <View testID="alert-panel" accessibilityViewIsModal style={{width:Math.min(width-20,390),maxHeight:Math.max(80,height-top-insets.bottom-12),backgroundColor:'#101b29',borderWidth:1,borderColor:'#39485a',borderRadius:14,overflow:'hidden'}}>
          <View style={[row,{paddingLeft:18,paddingRight:8,paddingVertical:10,justifyContent:'space-between'}]}>
            <View style={{gap:4}}><T size={18} weight="650">Thông báo bất thường</T>
              <T color={C.muted} size={12}>{market.day?'Phiên '+dateLabel(market.day)+' · Giờ New York':'Đang tải phiên…'}</T></View>
            <Button label="Đóng thông báo" style={{width:42,height:42}} onPress={close}><Icon name="close" size={17}/></Button>
          </View>
          <ScrollView style={{flexGrow:0,flexShrink:1}} contentContainerStyle={{paddingHorizontal:18,paddingBottom:10}}>
            {alerts.map(({symbol,start,end,peak})=><View key={symbol+'-'+start} style={[row,{justifyContent:'space-between',paddingVertical:12,borderTopWidth:1,borderColor:C.line}]}>
              <View style={{gap:4}}><View style={[row,{gap:7}]}><Dot color={C.alarm}/><T weight="700">{symbol}</T></View>
                <T size={12} color={C.muted} style={{fontFamily:mono}}>{clock(market.open,start)} – {clock(market.open,end)}</T></View>
              <View style={{alignItems:'flex-end',gap:4}}><T size={11} color={C.muted}>EBM cao nhất</T><T color={C.white} style={{fontFamily:mono}}>{number(peak,4)}</T></View>
            </View>)}
            {count===0&&<T style={{paddingVertical:14}} size={13} color={C.muted}>Chưa có cảnh báo tại mốc phát này.</T>}
          </ScrollView>
        </View>
      </View>
    </Modal>}
  </>;
}
