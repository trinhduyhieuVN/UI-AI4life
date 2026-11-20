import {useEffect, useState} from 'react';
import {Platform} from 'react-native';
import {apiOrigin} from './market';

export function useHeadlines() {
  const [data,setData] = useState(null);
  const [offline,setOffline] = useState(false);
  useEffect(() => {
    let active = true, socket, retry, poll, controller;
    const base = apiOrigin || (Platform.OS === 'web' ? window.location.origin : '');
    function accept(packet) {
      if (active) {
        setData(packet);
        setOffline(false);
      }
    }
    async function read() {
      if (!active || controller || socket?.readyState === WebSocket.OPEN) return;
      controller = new AbortController();
      const timeout = setTimeout(() => controller?.abort(), 10000);
      try {
        const response = await fetch(base + '/api/v1/news', {signal:controller.signal});
        if (!response.ok) throw Error();
        const packet = await response.json();
        if (socket?.readyState !== WebSocket.OPEN) accept(packet);
      } catch {
        if (active && socket?.readyState !== WebSocket.OPEN) setOffline(true);
      } finally {
        clearTimeout(timeout);
        controller = null;
      }
    }
    function connect() {
      socket = new WebSocket(base.replace(/^http/, 'ws') + '/api/v1/news/stream');
      socket.onmessage = event => accept(JSON.parse(event.data));
      socket.onerror = () => socket.close();
      socket.onclose = () => {
        if (!active) return;
        read();
        retry = setTimeout(connect, 10000);
      };
    }
    read();
    connect();
    poll = setInterval(read, 15000);
    return () => {
      active = false;
      clearTimeout(retry);
      clearInterval(poll);
      controller?.abort();
      socket.onclose = socket.onerror = null;
      socket.close();
    };
  }, []);
  return {data,offline};
}
