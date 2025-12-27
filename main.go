package main

import (
    "fmt"
    "net/http"
    "strconv"
)

// Sieve of Eratosthenes
// Scales CPU (loops) and RAM (allocating slices) simultaneously
func sieveOfEratosthenes(n int) []int {
    // 1. ALLOCATE MEMORY (RAM Scaling)
    // We use an int array instead of bool to consume more RAM per request
    // An int is usually 8 bytes on 64-bit systems.
    integers := make([]int8, n+1) 
    
    var primes []int

    // 2. BURN CPU (CPU Scaling)
    for i := 2; i <= n; i++ {
        if integers[i] == 0 {
            primes = append(primes, i) // Dynamic allocation
            // Mark multiples
            for j := i * i; j <= n; j += i {
                integers[j] = 1
            }
        }
    }
    return primes
}

func handler(w http.ResponseWriter, r *http.Request) {
    keys, ok := r.URL.Query()["n"]
    if !ok || len(keys[0]) < 1 {
        fmt.Fprintf(w, "Please provide 'n', e.g., /primes?n=100000")
        return
    }

    n, _ := strconv.Atoi(keys[0])
    
    // Safety cap to prevent accidental OOM during your PoC if you go too crazy
    if n > 20000000 { 
        fmt.Fprintf(w, "Limit capped at 20M for safety") 
        return
    }

    result := sieveOfEratosthenes(n)
    
    // We only print the count to save network bandwidth, 
    // but the RAM was already consumed during calculation.
    fmt.Fprintf(w, "Found %d primes up to %d\n", len(result), n)
}

func main() {
    http.HandleFunc("/primes", handler)
    fmt.Println("Sieve Server listening on port 8080...")
    http.ListenAndServe(":8080", nil)
}
