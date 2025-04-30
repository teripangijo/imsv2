// src/contexts/CartContext.jsx
import React, { createContext, useState, useContext, useReducer, useEffect } from 'react';

// 1. Buat Context (TAMBAHKAN 'export' di sini)
export const CartContext = createContext(null); // <-- Tambahkan export

// 2. Definisikan Reducer (Tetap sama)
const cartReducer = (state, action) => {
  switch (action.type) {
    case 'ADD_ITEM': {
      const existingItemIndex = state.items.findIndex(
        (item) => item.variant.id === action.payload.variant.id
      );
      if (existingItemIndex > -1) {
        const updatedItems = [...state.items];
        updatedItems[existingItemIndex].quantity += action.payload.quantity;
        if (updatedItems[existingItemIndex].quantity <= 0) {
           updatedItems.splice(existingItemIndex, 1);
        }
        return { ...state, items: updatedItems };
      } else {
        if (action.payload.quantity <= 0) return state;
        return { ...state, items: [...state.items, action.payload] };
      }
    }
    case 'REMOVE_ITEM': {
      const updatedItems = state.items.filter(
        (item) => item.variant.id !== action.payload.variantId
      );
      return { ...state, items: updatedItems };
    }
    case 'UPDATE_QUANTITY': {
      const updatedItems = state.items.map((item) => {
        if (item.variant.id === action.payload.variantId) {
          const newQuantity = Math.max(0, action.payload.quantity);
          if (newQuantity === 0) {
             return null;
          }
          return { ...item, quantity: newQuantity };
        }
        return item;
      }).filter(item => item !== null);
      return { ...state, items: updatedItems };
    }
    case 'CLEAR_CART': {
      return { ...state, items: [] };
    }
    case 'LOAD_CART': {
        return { ...state, items: action.payload.items || [] };
    }
    default:
      return state;
  }
};

// 3. Buat Provider Component (Tetap sama)
export function CartProvider({ children }) {
  const initialState = { items: [] };
  const [cartState, dispatch] = useReducer(cartReducer, initialState);

  // Load cart from localStorage on initial load
  useEffect(() => {
      try {
          const savedCart = localStorage.getItem('shoppingCart');
          if (savedCart) {
              const parsedCart = JSON.parse(savedCart);
              if(Array.isArray(parsedCart)) {
                  dispatch({ type: 'LOAD_CART', payload: { items: parsedCart } });
              } else {
                  localStorage.removeItem('shoppingCart');
              }
          }
      } catch (error) {
           localStorage.removeItem('shoppingCart');
      }
  }, []);

  // Save cart to localStorage whenever items change
  useEffect(() => {
    if (cartState.items.length > 0 || localStorage.getItem('shoppingCart')) {
        try {
            localStorage.setItem('shoppingCart', JSON.stringify(cartState.items));
        } catch (error) {
             console.error("Failed to save cart to localStorage:", error);
        }
    }
  }, [cartState.items]);

  // Cart manipulation functions (Tetap sama)
  const addToCart = (variant, quantity = 1) => {
    if (!variant || typeof variant.id === 'undefined') { return; }
    dispatch({ type: 'ADD_ITEM', payload: { variant, quantity } });
    console.log(`Added ${quantity} of ${variant.name || variant.variant_name} (ID: ${variant.id}) to cart.`);
  };
  const removeFromCart = (variantId) => { dispatch({ type: 'REMOVE_ITEM', payload: { variantId } }); console.log(`Removed variant ID: ${variantId} from cart.`); };
  const updateQuantity = (variantId, quantity) => { dispatch({ type: 'UPDATE_QUANTITY', payload: { variantId, quantity } }); console.log(`Updated quantity for variant ID: ${variantId} to ${quantity}.`); };
  const clearCart = () => { dispatch({ type: 'CLEAR_CART' }); localStorage.removeItem('shoppingCart'); console.log('Cart cleared.'); };

  // Context value (Tetap sama)
  const value = {
    cartItems: cartState.items,
    itemCount: cartState.items.reduce((sum, item) => sum + item.quantity, 0),
    addToCart,
    removeFromCart,
    updateQuantity,
    clearCart,
  };

  return <CartContext.Provider value={value}>{children}</CartContext.Provider>;
}

// 4. Buat Custom Hook (Tetap sama)
export function useCart() {
  const context = useContext(CartContext);
  if (context === undefined) {
    throw new Error('useCart must be used within a CartProvider');
  }
  return context;
}
