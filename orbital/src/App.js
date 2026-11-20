import React, {useCallback, useMemo, useState} from 'react';
import { Linking, Platform, StatusBar, StyleSheet, View, useWindowDimensions } from 'react-native';
import { SafeAreaProvider, SafeAreaView } from 'react-native-safe-area-context';
import { apiOrigin, clock, dateLabel, number, snapshot, useMarket, worlds } from './market';
import { Button, C, Dot, Icon, row, statusColor, statusName, T } from './ui';
import { OrbitScene } from './OrbitScene';
import { Details } from './Details';
import { card, Dialog, Header, ReplayPill } from './Controls';

function HoverInfo({world,stat,time,x,y,width,height}) {
  const boxWidth=Math.min(250,width-20);
  const left=x+boxWidth+22<width?x+18:Math.max(10,x-boxWidth-18);
  const top=Math.max(65,Math.min(y-16,height-194));
  return <View pointerEvents="none" testID="planet-tooltip" style={[card,{position:'absolute',left,top,width:boxWidth,padding:15,gap:8,backgroundColor:'#0c1725f5'}]}>
    <View style={[row,{justifyContent:'space-between'}]}><T size={19} weight="700">{world.s}</T><T size={10} color={C.muted}>{time} ET</T></View>
    <T size={12} color={C.muted}>{world.name} · {world.sector}</T>
    <View style={[row,{gap:8,alignItems:'baseline'}]}><T size={19} weight="600">{number(stat.close)} USD</T>
      {stat.change!=null&&<T size={11} color={stat.change>=0?C.mint:C.alarm}>{stat.change>=0?'+':''}{number(stat.change)}%</T>}</View>
    <View style={[row,{gap:5}]}><Dot color={statusColor(stat.alert)}/><T size={12} color={statusColor(stat.alert)}>{statusName(stat.alert)}</T></View>
    <T size={11} color={C.muted}>EBM {number(stat.last?.energy,4)}  /  ngưỡng {number(stat.last?.threshold,4)}</T>
  </View>;
}

function Observatory() {
  const {width,height}=useWindowDimensions(),small=width<620;
  const market=useMarket();
  const [hover,setHover]=useState(null),[touchSymbol,setTouchSymbol]=useState(null),[dates,setDates]=useState(false);
  const stats=useMemo(()=>Object.fromEntries(worlds.map(w=>[w.s,snapshot(market.frame?.bySymbol[w.s])])),[market.frame]);
  const days=useMemo(()=>[...new Set(market.catalog.map(s=>s.day))],[market.catalog]);
  const time=clock(market.open,market.frame?.minute??0);
  const inspect=useCallback((s,e)=>{
    if(Platform.OS!=='web'||!window.matchMedia('(any-hover: hover)').matches)return;
    const bounds=e.currentTarget?.getBoundingClientRect?.();
    if(!bounds)return;
    setHover({s,x:bounds.right,y:bounds.top+bounds.height*.38});
  },[]);
  const leave=useCallback(s=>setHover(prev=>prev?.s===s?null:prev),[]);
  const select=useCallback((s,e)=>{
    if(Platform.OS==='web'&&window.matchMedia('(any-hover: hover)').matches&&e.nativeEvent?.pointerType!=='touch') {
      inspect(s,e);return;
    }
    setHover(null);setTouchSymbol(s);
  },[inspect]);
  function openChart() {
    const query='/?view=terminal&mode=historical&symbol='+touchSymbol+'&day='+market.day+'&minute='+(market.frame?.minute??0);
    if(Platform.OS==='web')window.location.assign(query);else Linking.openURL(apiOrigin+query);
  }
  return <SafeAreaView style={{flex:1,backgroundColor:C.bg}}>
    <StatusBar barStyle="light-content"/>
    <View style={{flex:1}}>
      <View style={StyleSheet.absoluteFill}>
        <OrbitScene stats={stats} selected={hover?.s??touchSymbol} onSelect={select} onInspect={inspect} onLeave={leave} compact={small}/>
      </View>
      <Header small={small} market={market}/>
      {hover&&!dates&&<HoverInfo {...hover} width={width} height={height} world={worlds.find(w=>w.s===hover.s)} stat={stats[hover.s]} time={time}/>}
      <ReplayPill market={market} small={small} onDates={()=>{setHover(null);setDates(true);}}/>
      {!!market.error&&<View style={[card,row,{position:'absolute',alignSelf:'center',bottom:78,padding:12,gap:12,maxWidth:'96%'}]}><T color={C.alarm} style={{flexShrink:1}}>{market.error}</T><Button label="Thử lại" onPress={market.retry}><T>Thử lại</T></Button></View>}
    </View>
    {dates&&<Dialog label="Chọn phiên" small={small} onClose={()=>setDates(false)}><View style={{padding:20,gap:9}}>
      <View style={[row,{justifyContent:'space-between'}]}><T size={20} weight="600">Phiên đủ 8 mã</T><Button label="Đóng chọn phiên" onPress={()=>setDates(false)}><Icon name="close"/></Button></View>
      {days.map(d=><Button key={d} label={dateLabel(d)} selected={market.day===d} onPress={()=>{market.changeDay(d);setDates(false);}} style={{height:40,paddingHorizontal:10,justifyContent:'space-between',backgroundColor:d===market.day?'#23303a':undefined}}>
        <T size={14}>{dateLabel(d)}</T><T size={12} color={C.muted}>8 mã</T></Button>)}
    </View></Dialog>}
    {!!touchSymbol&&<Dialog label={touchSymbol} small={small} onClose={()=>setTouchSymbol(null)}>
      <Details world={worlds.find(w=>w.s===touchSymbol)} stat={stats[touchSymbol]} time={time} onClose={()=>setTouchSymbol(null)} onTerminal={stats[touchSymbol].last?openChart:null}/>
    </Dialog>}
  </SafeAreaView>;
}
export default function App(){return <SafeAreaProvider><Observatory/></SafeAreaProvider>;}
