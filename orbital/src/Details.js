import React from 'react';
import { View } from 'react-native';
import Svg, { Defs, LinearGradient, Path, Stop } from 'react-native-svg';
import { number } from './market';
import { Button, C, Caption, Dot, Icon, mono, Planet, row, statusColor, statusName, T } from './ui';

export function PriceLine({prices,up}) {
  if(prices.length<2)return <View style={{height:62,justifyContent:'center'}}><T size={11} color={C.dim}>Chờ thêm giao dịch để vẽ đường giá.</T></View>;
  const vals=prices.map(p=>p.close),lo=Math.min(...vals),hi=Math.max(...vals),color=up?C.mint:C.alarm;
  const points=prices.map(p=>[2+(p.minute-prices[0].minute)/(prices[prices.length-1].minute-prices[0].minute)*276,hi===lo?31:4+(hi-p.close)/(hi-lo)*50]);
  const line=points.map(([x,y],i)=>(i?'L':'M')+x.toFixed(1)+' '+y.toFixed(1)).join(' ');
  return <Svg width="100%" height={64} viewBox="0 0 280 64" preserveAspectRatio="none">
    <Defs><LinearGradient id="priceFill" x1="0" y1="0" x2="0" y2="1"><Stop offset="0" stopColor={color} stopOpacity=".24"/><Stop offset="1" stopColor={color} stopOpacity="0"/></LinearGradient></Defs>
    <Path d="M0 32h280" stroke="#27394a" strokeDasharray="3 5"/><Path d={line+' L278 64 L2 64 Z'} fill="url(#priceFill)"/><Path d={line} stroke={color} strokeWidth="1.6" fill="none"/>
  </Svg>;
}
export function Details({world,stat,time,onTerminal,onClose}) {
  const {last,close,open,change,alert,prices,volume}=stat, color=statusColor(alert);
  const ratio=last?.threshold>0?last.energy/last.threshold:null;
  return <View style={{flex:1,padding:21,gap:15}}>
    <View style={[row,{justifyContent:'space-between'}]}><Caption>CHI TIẾT CỔ PHIẾU</Caption>{onClose?<Button label="Đóng chi tiết" onPress={onClose} style={{padding:7}}><Icon name="close"/></Button>:<Icon name="orbit" color={C.dim} size={17}/>}</View>
    <View style={[row,{gap:11}]}><Planet tile={world.tile} size={46}/><View style={{flex:1,gap:1}}><T size={24} weight="700">{world.s}</T><T size={12} color={C.muted}>{world.name}</T></View></View>
    <View style={{gap:4}}><T size={10} color={C.muted}>Giá khớp gần nhất · USD</T>
      <View style={[row,{alignItems:'baseline',gap:9}]}><T size={35} weight="600" style={{letterSpacing:-1.4}}>{number(close)}</T>
      <T size={12} color={change===null?C.dim:change>=0?C.mint:C.alarm}>{change===null?'—':(change>=0?'+':'')+number(change)+'%'}</T></View>
      <PriceLine prices={prices} up={change>=0}/>
      <View style={[row,{justifyContent:'space-between'}]}><T size={10} color={C.dim}>09:30</T><T size={10} color={C.dim}>{time} ET</T></View>
    </View>
    <View style={{height:1,backgroundColor:C.line}}/>
    <View style={[row,{justifyContent:'space-between',flexWrap:'wrap',gap:6}]}>
      <T size={13} weight="600">Tín hiệu mô hình</T>
      <View style={[row,{gap:6,paddingHorizontal:8,paddingVertical:4,borderRadius:12,backgroundColor:alert===null?'#1b2632':alert?'#392820':'#17312e'}]}><Dot color={color}/><T size={10} color={color} weight="600">{statusName(alert)}</T></View>
    </View>
    <View style={{gap:7}}>{[['Năng lượng EBM',number(last?.energy,4)],['Ngưỡng cảnh báo',number(last?.threshold,4)],['Khối lượng đã khớp',last?number(volume,0):'—'],['Giá mở cửa',number(open)]].map(([label,value])=><View key={label} style={[row,{justifyContent:'space-between'}]}><T size={12} color={C.muted}>{label}</T><T size={12} style={{fontFamily:mono}}>{value}</T></View>)}</View>
    {ratio!==null&&<T size={11} color={C.muted} style={{lineHeight:16}}>{alert?'Điểm vượt ngưỡng tại '+time+' ET.':'Điểm nằm trong ngưỡng tại '+time+' ET.'}</T>}
    {onTerminal&&<Button label="Mở biểu đồ giá" onPress={onTerminal} style={{marginTop:'auto',borderWidth:1,borderColor:C.line,height:38,backgroundColor:'#142131'}}><T size={12} weight="600">Mở biểu đồ giá</T><Icon name="arrow" size={14}/></Button>}
  </View>;
}
